"""Prepare a transposed publication run from a completed ROCKY run.

Runs in the existing CPU score Pod, using the same Python environment as
publish_scores.py. The original run is never modified.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def transpose_midi(source: Path, target: Path, semitones: int) -> None:
    import pretty_midi

    score = pretty_midi.PrettyMIDI(str(source))
    for track in score.instruments:
        if track.is_drum:
            continue
        for note in track.notes:
            shifted = note.pitch + semitones
            if not 0 <= shifted <= 127:
                raise ValueError(f"MIDI pitch {note.pitch} cannot move by {semitones} semitones")
            note.pitch = shifted
    for signature in score.key_signature_changes:
        mode = 12 if signature.key_number >= 12 else 0
        signature.key_number = mode + (signature.key_number - mode + semitones) % 12
    target.parent.mkdir(parents=True, exist_ok=True)
    score.write(str(target))


def transpose_gp5(source: Path, target: Path, semitones: int) -> None:
    import guitarpro

    song = guitarpro.parse(str(source))
    shifted = copy.deepcopy(song)
    for index, track in enumerate(shifted.tracks):
        if track.isPercussionTrack:
            continue
        try:
            for measure in track.measures:
                for voice in measure.voices:
                    for beat in voice.beats:
                        for note in beat.notes:
                            if note.type in (guitarpro.NoteType.tie, guitarpro.NoteType.dead):
                                continue
                            fret = note.value + semitones
                            if not 0 <= fret <= track.fretCount:
                                raise ValueError(f"fret outside range in measure {measure.number}")
                            note.value = fret
        except ValueError:
            # Retune only the part that cannot use shifted frets. Keep the
            # original fret numbers, including tied notes, for this track.
            shifted.tracks[index] = copy.deepcopy(song.tracks[index])
            for string in shifted.tracks[index].strings:
                string.value += semitones
    def shifted_key(key):
        fifths, minor = key.value
        pitch = (fifths * 7 + (9 if minor else 0) + semitones) % 12
        return min((candidate for candidate in guitarpro.KeySignature
                    if candidate.value[1] == minor and
                    (candidate.value[0] * 7 + (9 if minor else 0)) % 12 == pitch),
                   key=lambda candidate: (abs(candidate.value[0] - fifths),
                                          abs(candidate.value[0])))
    shifted.key = shifted_key(shifted.key)
    for header in shifted.measureHeaders:
        header.keySignature = shifted_key(header.keySignature)
    target.parent.mkdir(parents=True, exist_ok=True)
    guitarpro.write(shifted, str(target))


def prepare(source: Path, target: Path, semitones: int) -> None:
    if not -12 <= semitones <= 12 or semitones == 0:
        raise ValueError("semitones must be between -12 and 12, excluding zero")
    source = source.resolve()
    target = target.resolve()
    if target == source or source in target.parents and target.parent != source / "transpositions":
        raise ValueError("invalid transposition target")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("source run is incomplete")
    if not (source / "scores" / "score_outputs.json").is_file():
        raise ValueError("source score publication is incomplete")
    target.mkdir(parents=True, exist_ok=True)
    transpose_midi(source / "full_score.mid", target / "full_score.mid", semitones)
    for key, fallback in (("guitar_score_dir", "guitar"), ("guitar_extra_dir", ""),
                          ("bass_score_dir", "bass")):
        relative = manifest.get(key, fallback)
        if not relative:
            continue
        directory = Path(relative)
        if directory.is_absolute() or ".." in directory.parts:
            raise ValueError(f"invalid GP5 directory: {relative}")
        for gp5 in (source / directory).glob("*.gp5"):
            transpose_gp5(gp5, target / directory / gp5.name, semitones)
    manifest["transposed_semitones"] = semitones
    manifest.pop("score_outputs", None)
    manifest.pop("score_publication", None)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("semitones", type=int)
    args = parser.parse_args()
    prepare(args.source, args.target, args.semitones)


if __name__ == "__main__":
    main()
