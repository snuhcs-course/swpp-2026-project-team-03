#!/usr/bin/env python3
"""Measure the numbers behind the rule-gate thresholds (no model, CPU only).

Give it unified.py run directories that still have stems/ (the server
deletes stems/ after a song is complete, so use --no-publish runs or copy
the stems first). For each run it prints the input-check values, and when
stem_midi/ exists, how loud each transcribed note is relative to its stem's
playing level:

    python measure_gates.py runs/band14-* runs/nonband-* --json gates.json
    python measure_gates.py runs/hanpe --rest guitar:212.0-224.5 --rest bass:212.0-224.5

--rest marks a passage (seconds) where the instrument is known to rest, e.g.
bars 115-120 of 한페; notes there are reported separately from the others,
which is what the note floor has to separate.

Pick min_band_ratio below the lowest band song with a margin and above the
non-band audio; pick note_floor_db between the "rest" and "played" notes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pretty_midi

from rule_gates import BAND_STEMS, GateConfig, InputRejected, check_input, frame_power, note_levels, reference_level
from unified import family


def parse_rest(raw: str) -> tuple[str, float, float]:
    stem, span = raw.split(":", 1)
    start, end = span.split("-", 1)
    return stem, float(start), float(end)


def percentiles(values) -> dict:
    if not len(values):
        return {}
    return {str(p): round(float(np.percentile(values, p)), 1) for p in (1, 5, 10, 25, 50, 90)}


def measure_run(run: Path, cfg: GateConfig, rests: list[tuple[str, float, float]]) -> dict:
    stems = run / "stems"
    try:
        result = {"input_check": check_input(stems, cfg), "would_reject": None}
    except InputRejected as exc:
        result = {"input_check": exc.detail, "would_reject": exc.code}
    duration = result["input_check"]["duration_sec"]
    notes_report = {}
    for stem in BAND_STEMS:
        midi_path = run / "stem_midi" / f"{stem}.mid"
        if not midi_path.is_file():
            continue
        power, rate = frame_power(stems / f"{stem}.wav", cfg.hop)
        ref = reference_level(power, cfg)
        played, resting = [], []
        for track in pretty_midi.PrettyMIDI(str(midi_path)).instruments:
            if family(track) != stem or not track.notes:
                continue
            rel = note_levels(track.notes, power, rate, cfg, drums=track.is_drum) - ref
            for note, value in zip(track.notes, rel):
                in_rest = any(s == stem and a <= note.start < b for s, a, b in rests)
                (resting if in_rest else played).append(float(value))
        everything = played + resting
        notes_report[stem] = {
            "reference_dbfs": round(ref, 1),
            "notes": len(everything),
            "notes_per_minute": round(len(everything) / max(duration / 60, 1 / 60), 1),
            "relative_db": percentiles(everything),
            "dropped_at": {str(f): int(sum(v < f for v in everything)) for f in (-25, -30, -35, -40, -45)},
        }
        if any(s == stem for s, _, _ in rests):
            notes_report[stem]["played_relative_db"] = percentiles(played)
            notes_report[stem]["rest_relative_db"] = percentiles(resting)
            notes_report[stem]["rest_notes"] = len(resting)
    result["notes"] = notes_report
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", type=Path, nargs="+", help="unified.py output directories")
    parser.add_argument("--rest", action="append", default=[], type=parse_rest,
                        help="STEM:START-END seconds where that instrument rests (repeatable)")
    parser.add_argument("--json", type=Path, help="also write all numbers to this file")
    args = parser.parse_args()
    cfg = GateConfig()
    results = {}
    for run in args.runs:
        results[run.name] = measure_run(run, cfg, args.rest)
        check = results[run.name]["input_check"]
        verdict = results[run.name]["would_reject"] or "accept"
        print(f"{run.name}: band_ratio={check['band_ratio']:.3f} level={check['level_dbfs']:.1f} dBFS "
              f"duration={check['duration_sec']:.0f}s -> {verdict}")
        for stem, info in results[run.name]["notes"].items():
            line = (f"  {stem:6} notes={info['notes']:5} /min={info['notes_per_minute']:6} "
                    f"rel dB p5={info['relative_db'].get('5')} p50={info['relative_db'].get('50')} "
                    f"dropped@-30={info['dropped_at']['-30']}")
            if "rest_notes" in info:
                line += (f" | rest notes={info['rest_notes']} rest p50={info['rest_relative_db'].get('50')}"
                         f" played p5={info['played_relative_db'].get('5')}")
            print(line)
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
