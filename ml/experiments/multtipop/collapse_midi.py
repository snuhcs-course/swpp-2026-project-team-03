#!/usr/bin/env python3
"""Collapse a multitrack MIDI file into ROCKY's four supported instruments.

Family rule (General MIDI program numbers, zero-indexed):
  keyboard = 0-7 (pianos) and 16-23 (organs)
  guitar   = 24-31
  bass     = 32-39
  drums    = any track on MIDI channel 10
Everything else (strings, brass, synth leads/pads, voices, ...) is dropped and
listed in the report; it is never forced into one of the four families.

The input file is only read.  The collapsed copy is written to OUTPUT.
"""
from __future__ import annotations

import argparse, json, re
from pathlib import Path

import pretty_midi

FAMILY_ORDER = ["keyboard", "guitar", "bass", "drums"]
FAMILY_PROGRAMS = {
    "keyboard": [*range(0, 8), *range(16, 24)],
    "guitar": range(24, 32),
    "bass": range(32, 40),
}
# Program written to the collapsed track of each family.
OUTPUT_PROGRAM = {"keyboard": 0, "guitar": 25, "bass": 33, "drums": 0}
# MulTTiPop references come from Lakh MIDI files, where the sung melody is a
# normal instrument track (flute, sax, piano, ...) recognisable only by name.
VOCAL_TRACK_NAME = re.compile(r"vocal|vox|voice|melod|singer|lyric", re.IGNORECASE)


def family(instrument, drop_vocal_tracks=False):
    if instrument.is_drum:
        return "drums"
    if drop_vocal_tracks and VOCAL_TRACK_NAME.search(instrument.name or ""):
        return "vocal"
    return next((name for name, programs in FAMILY_PROGRAMS.items() if instrument.program in programs), "other")


def collapse(midi, drop_vocal_tracks=False):
    """Return (collapsed PrettyMIDI, report dict) for an already loaded file."""
    tracks = {name: pretty_midi.Instrument(OUTPUT_PROGRAM[name], is_drum=name == "drums", name=name) for name in FAMILY_ORDER}
    report = {"notes": {name: 0 for name in [*FAMILY_ORDER, "vocal", "other"]}, "tracks": []}
    for instrument in midi.instruments:
        label = family(instrument, drop_vocal_tracks)
        report["notes"][label] += len(instrument.notes)
        report["tracks"].append({
            "name": instrument.name.strip(),
            "program": None if instrument.is_drum else int(instrument.program),
            "gm_name": "Drums" if instrument.is_drum else pretty_midi.program_to_instrument_name(instrument.program),
            "notes": len(instrument.notes),
            "family": label,
        })
        if label in tracks:
            tracks[label].notes.extend(instrument.notes)
    collapsed = pretty_midi.PrettyMIDI()
    for name in FAMILY_ORDER:
        if tracks[name].notes:
            tracks[name].notes.sort(key=lambda note: (note.start, note.pitch))
            collapsed.instruments.append(tracks[name])
    return collapsed, report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--drop-vocal-tracks", action="store_true",
                        help="drop tracks whose name marks them as the sung melody (use for MulTTiPop references)")
    parser.add_argument("--report", type=Path, help="write the per-track mapping as JSON")
    args = parser.parse_args()
    if args.output.resolve() == args.input.resolve():
        parser.error("OUTPUT must differ from INPUT; the source MIDI is never overwritten")
    collapsed, report = collapse(pretty_midi.PrettyMIDI(str(args.input)), args.drop_vocal_tracks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    collapsed.write(str(args.output))
    if args.report:
        args.report.write_text(json.dumps({"input": str(args.input), **report}, indent=2, ensure_ascii=False))
    print(f"{args.input} -> {args.output}  " + "  ".join(f"{name}={count}" for name, count in report["notes"].items()))


if __name__ == "__main__":
    main()
