#!/usr/bin/env python3
"""Publish full-band and instrument PDF scores from a completed unified run.

Run this in a CPU environment with MuseScore, Node/Playwright, and the
gp5-to-pdf module. Guitar and bass use their completed GP5 tablatures;
full-band, keyboard, and drums use the final assembled MIDI.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

import pretty_midi


# MuseScore 3's stock drumset drops these GM pitches during MIDI import.
# Map them only in notation inputs; full_score.mid remains untouched.
DRUM_NOTATION_MAP = {39: 38, 70: 54, 82: 44}  # clap->snare, maracas->tambourine, shaker->pedal hi-hat


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def family(track: pretty_midi.Instrument) -> str:
    if track.is_drum:
        return "drums"
    name = track.name.lower()
    if name.startswith(("piano:", "ai generated piano:")) or track.program in range(0, 8) or track.program in range(16, 24):
        return "piano"
    if track.program in range(24, 32):
        return "guitar"
    if track.program in range(32, 40):
        return "bass"
    raise ValueError(f"Unexpected final-score track: {track.name!r}, program={track.program}")


def pdf_pages(path: Path, pdfinfo: str) -> int:
    if not path.is_file() or path.stat().st_size < 1000:
        raise ValueError(f"PDF missing or too small: {path}")
    result = subprocess.run([pdfinfo, str(path)], capture_output=True, text=True, check=True)
    match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match or int(match.group(1)) < 1:
        raise ValueError(f"PDF has no readable pages: {path}")
    return int(match.group(1))


def choose_gp5(directory: Path, part: str) -> Path:
    candidates = sorted(directory.glob("*.gp5"))
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one final {part} GP5 in {directory}, found {len(candidates)}")
    if candidates[0].stat().st_size == 0:
        raise ValueError(f"Empty {part} GP5: {candidates[0]}")
    return candidates[0]


def export_part_midi(score: pretty_midi.PrettyMIDI, part: str, path: Path) -> list[dict]:
    tracks = [copy.deepcopy(track) for track in score.instruments if track.notes and family(track) == part]
    if not tracks:
        raise ValueError(f"Final score has no {part} notes")
    result = copy.deepcopy(score)
    result.instruments = tracks
    path.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(path))
    return [{"name": str(track.name), "program": int(track.program), "notes": len(track.notes)} for track in tracks]


def notation_midi(source: pretty_midi.PrettyMIDI, path: Path) -> dict[int, int]:
    """Make a render-only copy so unsupported drum hits stay visible in PDF."""
    rendered = copy.deepcopy(source)
    mapped = {pitch: 0 for pitch in DRUM_NOTATION_MAP}
    for track in rendered.instruments:
        if track.is_drum:
            for note in track.notes:
                if note.pitch in DRUM_NOTATION_MAP:
                    mapped[note.pitch] += 1
                    note.pitch = DRUM_NOTATION_MAP[note.pitch]
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered.write(str(path))
    return {pitch: count for pitch, count in mapped.items() if count}


def publish(run: Path, musescore: str, node: str, gp5_converter: Path, pdfinfo: str, force: bool) -> dict:
    final = run / "full_score.mid"
    manifest_path = run / "manifest.json"
    if not final.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Completed unified run must contain full_score.mid and manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("MIDI workflow is not complete")
    score = pretty_midi.PrettyMIDI(str(final))
    families = {family(track) for track in score.instruments if track.notes}
    if not families or not families <= {"guitar", "bass", "piano", "drums"}:
        raise ValueError(f"Unexpected band parts: {families}")
    out = run / "scores"
    out.mkdir(exist_ok=True)
    source_hash = sha256(final)
    outputs = {}

    def render(key: str, source: Path, converter: str, command: list[str], tracks: list[dict]) -> None:
        target = out / f"{key}.pdf"
        if force or not target.is_file() or target.stat().st_mtime < source.stat().st_mtime:
            target.unlink(missing_ok=True)
            subprocess.run(command, check=True)
        pages = pdf_pages(target, pdfinfo)
        outputs[key] = {"pdf": target.relative_to(run).as_posix(),
                        "source": source.relative_to(run).as_posix(), "converter": converter,
                        "tracks": tracks, "pages": pages, "bytes": target.stat().st_size,
                        "sha256": sha256(target)}

    full_render = out / "full_band_render.mid"
    drum_mapping_counts = notation_midi(score, full_render)
    render("full_band", full_render, "musescore-midi", [musescore, "-o", str(out / "full_band.pdf"), str(full_render)],
           [{"name": str(t.name), "program": int(t.program), "notes": len(t.notes)} for t in score.instruments if t.notes])
    for part in ("piano", "drums"):
        if part not in families:
            continue
        part_midi = out / f"{part}.mid"
        tracks = export_part_midi(score, part, part_midi)
        render_midi = out / f"{part}_render.mid" if part == "drums" else part_midi
        if part == "drums":
            notation_midi(pretty_midi.PrettyMIDI(str(part_midi)), render_midi)
        render(part, render_midi, "musescore-midi",
               [musescore, "-o", str(out / f"{part}.pdf"), str(render_midi)], tracks)
    for part in ("guitar", "bass"):
        if part not in families:
            continue
        gp5 = choose_gp5(run / part, part)
        render(part, gp5, "gp5-to-pdf",
               [node, str(gp5_converter), str(gp5), str(out / f"{part}.pdf"), "--timeout-ms", "180000"],
               [{"name": part, "source_gp5": gp5.relative_to(run).as_posix()}])

    contract = {"version": 1, "full_score_midi": final.relative_to(run).as_posix(), "full_score_midi_sha256": source_hash,
                "drum_notation_map": {str(k): v for k, v in DRUM_NOTATION_MAP.items()},
                "drum_notation_mapped_counts": {str(k): v for k, v in drum_mapping_counts.items()},
                "full_band": outputs["full_band"],
                "instruments": {part: outputs[part] for part in ("guitar", "bass", "piano", "drums") if part in outputs}}
    contract_path = out / "score_outputs.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["score_outputs"] = contract_path.relative_to(run).as_posix()
    manifest["score_publication"] = "complete"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="completed unified run directory")
    parser.add_argument("--musescore", default="musescore3")
    parser.add_argument("--node", default="node")
    parser.add_argument("--gp5-converter", type=Path,
                        default=Path("/data/rocky-unified/ml/gp5_to_pdf/convert.js"))
    parser.add_argument("--pdfinfo", default="pdfinfo")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = publish(args.run.resolve(), args.musescore, args.node,
                     args.gp5_converter.resolve(), args.pdfinfo, args.force)
    print(json.dumps({"full_band": result["full_band"]["pages"],
                      "instruments": {key: value["pages"] for key, value in result["instruments"].items()}}))


if __name__ == "__main__":
    main()
