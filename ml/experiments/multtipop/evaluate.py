#!/usr/bin/env python3
"""Score collapsed predictions against collapsed MulTTiPop references.

For every outputs/multtipop/<id>/ that holds reference_collapsed.mid and
<system>_collapsed.mid, report onset F1 (same pitch, onset within the
tolerance) per family, and Multi F1 where the family must match as well.

A family that is absent from the reference is left blank instead of scored 0,
so missing instruments do not pull the mean down.  This differs from the
BabySlakh table, which counted them as 0.
"""
from __future__ import annotations

import argparse, csv, warnings
from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi

from collapse_midi import FAMILY_ORDER

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def notes(path):
    """Return {family: [(onset, offset, pitch)]} of a collapsed MIDI file."""
    midi = pretty_midi.PrettyMIDI(str(path))
    return {inst.name: [(n.start, max(n.end, n.start + 1e-3), n.pitch) for n in inst.notes] for inst in midi.instruments}


def onset_f1(reference, estimate, tolerance):
    if not reference:
        return None
    if not estimate:
        return 0.0
    ri, rp = np.array([n[:2] for n in reference]), mir_eval.util.midi_to_hz(np.array([n[2] for n in reference]))
    ei, ep = np.array([n[:2] for n in estimate]), mir_eval.util.midi_to_hz(np.array([n[2] for n in estimate]))
    return mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=tolerance, offset_ratio=None)[2]


def multi(by_family):
    # shift each family into its own pitch range so matches cannot cross families
    return [(start, end, pitch + 128 * FAMILY_ORDER.index(name)) for name, items in by_family.items() for start, end, pitch in items]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("system", help="prediction name, e.g. muscriptor_medium or yourmt3")
    parser.add_argument("--outputs", type=Path, default=PROJECT_ROOT / "outputs/multtipop")
    parser.add_argument("--onset-tolerance", type=float, default=0.05, help="seconds (default 0.05)")
    args = parser.parse_args()
    warnings.filterwarnings("ignore")

    rows = []
    for folder in sorted(args.outputs.iterdir()):
        reference_path, estimate_path = folder / "reference_collapsed.mid", folder / f"{args.system}_collapsed.mid"
        if not (reference_path.exists() and estimate_path.exists()):
            continue
        reference, estimate = notes(reference_path), notes(estimate_path)
        scores = {name: onset_f1(reference.get(name, []), estimate.get(name, []), args.onset_tolerance) for name in FAMILY_ORDER}
        scores["multi"] = onset_f1(multi(reference), multi(estimate), args.onset_tolerance)
        rows.append({"id": folder.name,
                     "reference_notes": sum(map(len, reference.values())), "predicted_notes": sum(map(len, estimate.values())),
                     **{f"{name}_f1": "" if value is None else f"{value:.4f}" for name, value in scores.items()}})
    if not rows:
        parser.error(f"no folder under {args.outputs} has both reference_collapsed.mid and {args.system}_collapsed.mid")
    mean = {"id": "MEAN", "reference_notes": "", "predicted_notes": ""}
    for key in [f"{name}_f1" for name in [*FAMILY_ORDER, "multi"]]:
        values = [float(row[key]) for row in rows if row[key]]
        mean[key] = f"{np.mean(values):.4f}" if values else ""
    rows.append(mean)

    output = args.outputs / f"scores_{args.system}.csv"
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    for row in rows:
        print("  ".join(f"{value or '-':>11}" for value in row.values()))
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
