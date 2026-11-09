"""Full score: one MIDI with the processed guitar(s), the processed bass and the other instruments.

Track order: guitar(s) from skyline_tab.py -> bass from bass_tab.py -> other instruments of the
beat-aligned MIDI (piano, ...) -> drums. Guitar and bass tracks of the aligned MIDI are replaced, every
other track is copied unchanged. Time signature and resolution come from the aligned MIDI.
Only its initial tempo is used; later tempo changes are not preserved.
Each processed guitar part gets the sound (GM program) most of its notes had in the aligned MIDI;
nylon (24) becomes steel acoustic (25), since the TAB allows 20 frets and a classical guitar usually has 19.
Keyboard tracks (GM 0-7, 16-23) are made playable by two hands first (piano_playable.py; --no-keyboard-limit
copies them unchanged).

    python full_score.py song_aligned.mid guitar_out_dir/ bass_out_dir/ song_full_score.mid

guitar_out_dir: skyline_tab.py output (skyline_lead_rhythm.mid when split, guitar.mid otherwise)
bass_out_dir:   bass_tab.py output (bass.mid); if missing, the aligned MIDI's bass is dropped

Written with Claude (AI); reviewed by Soobin Jo.
"""
import argparse
import collections
import copy
from pathlib import Path

import pretty_midi

import piano_playable

NYLON, STEEL = 24, 25   # GM: Acoustic Guitar (nylon), Acoustic Guitar (steel)


def is_guitar(i):
    return not i.is_drum and 24 <= i.program <= 31


def is_bass(i):
    return not i.is_drum and 32 <= i.program <= 39


def guitar_tracks(guitar_dir):
    d = Path(guitar_dir)
    for name in ("skyline_lead_rhythm.mid", "guitar.mid"):
        if (d / name).exists():
            return pretty_midi.PrettyMIDI(str(d / name)).instruments
    raise FileNotFoundError(f"{d}: no skyline_lead_rhythm.mid or guitar.mid (run skyline_tab.py first)")


def part_sound(part, aligned, default=None):
    """Majority sound (GM program) of one processed guitar part.

    Each processed note votes with the program of the aligned guitar note it came from: same onset
    (skyline_tab keeps onsets), same pitch class (it may move notes by octaves), nearest pitch.
    Ties go to `default` (the aligned MIDI's first guitar track), then to the lowest program.
    Returns `default` when no note can be matched.
    """
    by_onset = collections.defaultdict(list)
    for i in aligned.instruments:
        if is_guitar(i):
            for n in i.notes:
                by_onset[round(n.start, 4)].append((n.pitch, i.program))
    votes = collections.Counter()
    for n in part.notes:
        cands = [c for c in by_onset.get(round(n.start, 4), []) if (c[0] - n.pitch) % 12 == 0]
        if cands:
            votes[min(cands, key=lambda c: abs(c[0] - n.pitch))[1]] += 1
    if not votes:
        return default
    top = max(votes.values())
    winners = sorted(p for p, v in votes.items() if v == top)
    return default if default in winners else winners[0]


def build(aligned, guitars, basses, keyboard_limit=True):
    """aligned: PrettyMIDI; guitars/basses: processed Instrument lists. Returns a new PrettyMIDI.
    keyboard_limit: make the keyboard tracks playable by two hands (piano_playable.process)."""
    if keyboard_limit:
        aligned, _ = piano_playable.process(aligned)
    out = pretty_midi.PrettyMIDI(initial_tempo=aligned.get_tempo_changes()[1][0], resolution=aligned.resolution)
    out.time_signature_changes = copy.deepcopy(aligned.time_signature_changes)
    out.key_signature_changes = copy.deepcopy(aligned.key_signature_changes)
    # each processed guitar part (lead, rhythm or the single guitar) takes its own majority sound
    first = next((i.program for i in aligned.instruments if is_guitar(i)), None)
    for g in guitars:
        g = copy.deepcopy(g)
        sound = part_sound(g, aligned, first)
        if sound == NYLON:
            sound = STEEL   # TAB allows 20 frets; a classical (nylon) guitar usually has 19
        if sound is not None:
            g.program = sound
        out.instruments.append(g)
    for b in basses:
        b = copy.deepcopy(b)
        b.name = "Bass (TAB processed)"
        out.instruments.append(b)
    rest = [i for i in aligned.instruments if not (is_guitar(i) or is_bass(i))]
    out.instruments += [copy.deepcopy(i) for i in rest if not i.is_drum] + [copy.deepcopy(i) for i in rest if i.is_drum]
    return out


def main(aligned_path, guitar_dir, bass_dir, out_path, keyboard_limit=True):
    aligned = pretty_midi.PrettyMIDI(str(aligned_path))
    bass_mid = Path(bass_dir) / "bass.mid"
    basses = pretty_midi.PrettyMIDI(str(bass_mid)).instruments if bass_mid.exists() else []
    if not basses:
        print(f"{bass_mid} not found: no bass track")
    if keyboard_limit:
        print("keyboard:", piano_playable.process(aligned)[1])
    out = build(aligned, guitar_tracks(guitar_dir), basses, keyboard_limit)
    out.write(str(out_path))
    print(" · ".join(f"{i.name} ({len(i.notes)})" for i in out.instruments) + f" -> {out_path}")
    return out


def cli(argv=None):
    p = argparse.ArgumentParser(description="Merge processed guitar/bass with the other instruments into one MIDI")
    p.add_argument("aligned", help="beat-aligned MIDI (ml/beat_align output)")
    p.add_argument("guitar_dir", help="skyline_tab.py output folder")
    p.add_argument("bass_dir", help="bass_tab.py output folder")
    p.add_argument("out", help="output MIDI")
    p.add_argument("--no-keyboard-limit", action="store_true", help="copy keyboard tracks unchanged")
    a = p.parse_args(argv)
    main(a.aligned, a.guitar_dir, a.bass_dir, a.out, not a.no_keyboard_limit)


if __name__ == "__main__":
    cli()
