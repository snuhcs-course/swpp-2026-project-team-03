#!/usr/bin/env python3
"""Evaluate BabySlakh MIDI-RWKV outputs with the paper's CP, GS and PCHE rules.

The official evaluator measures an infilled region of one target track. This
adapter keeps its metric formulas but evaluates the complete source bar range
and merges all excluded target stems into one reference track.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from miditok.utils import get_bars_ticks
from symusic import Score


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = PROJECT_ROOT.parent / "babyslakh_16k"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "ml" / "outputs" / "midi_rwkv_babyslakh"
OFFICIAL_METRICS_ROOT = (
    PROJECT_ROOT / "ml" / "external" / "MIDI-RWKV" / "MIDIMetrics" / "metrics"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merged_score(path: Path) -> Score:
    """Merge every track into one, matching the consolidated generation target."""
    score = Score(path)
    if not score.tracks:
        raise ValueError(f"No tracks in {path}")
    merged = copy.deepcopy(score.tracks[0])
    merged.notes = [
        copy.deepcopy(note) for track in score.tracks for note in track.notes
    ]
    score.tracks = [merged]
    return score


def full_track_bar_ticks(source: Score) -> np.ndarray:
    """Build the full window as MIDIMetricsProcessor does at the final bar."""
    ticks = list(get_bars_ticks(source))
    if len(ticks) < 2:
        raise ValueError("At least two bar ticks are required for evaluation")
    source_end = source.end()
    while ticks[-1] <= source_end:
        ticks.append(ticks[-1] + ticks[-1] - ticks[-2])
    return np.asarray(ticks, dtype=np.int64)


def chroma_matrix(score: Score, frame_ticks: np.ndarray) -> np.ndarray:
    """Official CP chroma representation: 16 frames/bar and half-bar smoothing."""
    notes = score.tracks[0].notes
    pitches = np.asarray([note.pitch for note in notes], dtype=int)
    durations = np.asarray([note.duration for note in notes], dtype=int)
    times = np.asarray([note.time for note in notes])
    vectors: list[np.ndarray] = []
    for start, end in zip(frame_ticks[:-1], frame_ticks[1:]):
        active = np.where((times < end) & (times + durations > start))[0]
        vector = np.zeros(12)
        for pitch in pitches[active]:
            vector[pitch % 12] += 1
        vectors.append(vector)
    matrix = np.asarray(vectors)
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)
    frame_size = 8
    return np.asarray(
        [
            np.mean(matrix[max(0, i - frame_size // 2) : i + frame_size // 2], axis=0)
            if len(matrix[max(0, i - frame_size // 2) : i + frame_size // 2])
            else np.zeros(12)
            for i in range(matrix.shape[0])
        ]
    )


def content_preservation(generated: Score, reference: Score, bars: np.ndarray) -> float:
    """Mean frame-wise cosine similarity from official ContentPreservationMetric."""
    frame_count = (len(bars) - 1) * 16
    frames = np.linspace(bars[0], bars[-1], num=frame_count + 1, endpoint=True)
    generated_chroma = chroma_matrix(generated, frames)
    reference_chroma = chroma_matrix(reference, frames)
    similarities = []
    for original, infilled in zip(reference_chroma, generated_chroma):
        denominator = np.linalg.norm(original) * np.linalg.norm(infilled)
        similarities.append(0.0 if denominator == 0 else float(np.dot(original, infilled) / denominator))
    return float(np.mean(similarities))


def groove_consistency(score: Score, bars: np.ndarray) -> float:
    """Official adjacent-bar onset-pattern GS at tpq//8 subdivisions."""
    bar_count = len(bars) - 1
    ticks_per_subdivision = score.tpq // 8
    if ticks_per_subdivision < 1:
        raise ValueError(f"Unsupported TPQ for GS: {score.tpq}")
    ticks_per_bar = max(int(end - start) for start, end in zip(bars[:-1], bars[1:]))
    subdivisions_per_bar = ticks_per_bar // ticks_per_subdivision
    patterns = np.zeros((bar_count, subdivisions_per_bar), dtype=bool)
    times = np.asarray([note.time for note in score.tracks[0].notes])
    for index, (start, end) in enumerate(zip(bars[:-1], bars[1:])):
        relative = times[(times >= start) & (times < end)] - start
        subdivisions = np.unique(relative // ticks_per_subdivision).astype(int)
        subdivisions = subdivisions[subdivisions < subdivisions_per_bar]
        patterns[index, subdivisions] = True
    hamming_distance = np.count_nonzero(patterns[:-1] != patterns[1:])
    return float(1 - hamming_distance / (subdivisions_per_bar * bar_count))


def pitch_class_histogram_entropy(score: Score, bars: np.ndarray) -> float | None:
    """Official base-2 entropy of note-on pitch-class probabilities."""
    pitches = [
        note.pitch
        for note in score.tracks[0].notes
        if bars[0] <= note.time < bars[-1]
    ]
    if not pitches:
        return None
    counts = np.zeros(12)
    for pitch in pitches:
        counts[pitch % 12] += 1
    probabilities = counts / counts.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(-np.nansum(probabilities * np.log2(probabilities)))


def stats(values: Iterable[float | None]) -> dict[str, Any]:
    valid = [float(value) for value in values if value is not None and not math.isnan(value)]
    return {
        "count": len(valid),
        "mean": statistics.fmean(valid) if valid else None,
        "std": statistics.pstdev(valid) if valid else None,
        "min": min(valid) if valid else None,
        "max": max(valid) if valid else None,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(rows),
        "CP": stats(row["CP"] for row in rows),
        "GS_generated": stats(row["GS_generated"] for row in rows),
        "GS_reference": stats(row["GS_reference"] for row in rows),
        "GS_absolute_difference": stats(row["GS_absolute_difference"] for row in rows),
        "PCHE_generated": stats(row["PCHE_generated"] for row in rows),
        "PCHE_reference": stats(row["PCHE_reference"] for row in rows),
        "PCHE_absolute_difference": stats(
            row["PCHE_absolute_difference"] for row in rows
        ),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    results_root = args.results_root.resolve()
    output_dir = results_root / "evaluation_cp_gs_pche"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifests = []
    for path in sorted(results_root.glob("Track*/**/manifest.json")):
        manifests.append((path, json.loads(path.read_text(encoding="utf-8"))))
    completed = [(path, item) for path, item in manifests if item["status"] == "completed"]
    if not completed:
        raise RuntimeError(f"No completed generation cases under {results_root}")

    rows: list[dict[str, Any]] = []
    for manifest_path, manifest in completed:
        case_dir = manifest_path.parent
        generated = merged_score(case_dir / "generated.mid")
        reference = merged_score(case_dir / "reference.mid")
        source = Score(dataset_root / manifest["track"] / "all_src.mid")
        bars = full_track_bar_ticks(source)
        if generated.tpq != reference.tpq or generated.tpq != source.tpq:
            raise ValueError(f"TPQ mismatch in {manifest['track']}/{manifest['target']}")

        cp = content_preservation(generated, reference, bars)
        gs_generated = groove_consistency(generated, bars)
        gs_reference = groove_consistency(reference, bars)
        pche_generated = None
        pche_reference = None
        if manifest["target"] != "Drums":
            pche_generated = pitch_class_histogram_entropy(generated, bars)
            pche_reference = pitch_class_histogram_entropy(reference, bars)
        rows.append(
            {
                "track": manifest["track"],
                "target": manifest["target"],
                "CP": cp,
                "GS_generated": gs_generated,
                "GS_reference": gs_reference,
                "GS_absolute_difference": abs(gs_generated - gs_reference),
                "PCHE_generated": pche_generated,
                "PCHE_reference": pche_reference,
                "PCHE_absolute_difference": (
                    abs(pche_generated - pche_reference)
                    if pche_generated is not None and pche_reference is not None
                    else None
                ),
                "evaluated_bars": len(bars) - 1,
                "generated_notes": len(generated.tracks[0].notes),
                "reference_notes": len(reference.tracks[0].notes),
                "generated_midi": str((case_dir / "generated.mid").resolve()),
                "reference_midi": str((case_dir / "reference.mid").resolve()),
            }
        )

    by_target = {
        target: aggregate([row for row in rows if row["target"] == target])
        for target in ("Piano", "Guitar", "Bass", "Drums")
    }
    status_counts = Counter(item["status"] for _, item in manifests)
    summary = {
        "method": {
            "name": "MIDI-RWKV MIDIMetrics CP, GS and PCHE",
            "adaptation": (
                "Official infilling formulas applied to the complete source bar range; "
                "all excluded target stems are merged into one reference track."
            ),
            "CP_direction": "higher is better",
            "GS_direction": "higher generated groove consistency is better",
            "PCHE_direction": "lower absolute difference from reference is better",
            "PCHE_drums": "not applicable, matching the official evaluation configuration",
            "official_source_hashes": {
                name: sha256(OFFICIAL_METRICS_ROOT / name)
                for name in (
                    "pattern_matching_metrics.py",
                    "rythm_metrics.py",
                    "pitch_metrics.py",
                )
            },
        },
        "generation_status_counts": dict(status_counts),
        "evaluated_case_count": len(rows),
        "excluded_from_metrics": [
            {"track": item["track"], "target": item["target"], "status": item["status"], "reason": item.get("reason") or item.get("error")}
            for _, item in manifests
            if item["status"] != "completed"
        ],
        "overall": aggregate(rows),
        "by_target": by_target,
    }
    write_csv(output_dir / "metrics_per_case.csv", rows)

    metric_lookup = {(row["track"], row["target"]): row for row in rows}
    all_case_rows = []
    for _, manifest in sorted(
        manifests, key=lambda item: (item[1]["track"], item[1]["target"])
    ):
        metric = metric_lookup.get((manifest["track"], manifest["target"]))
        all_case_rows.append(
            {
                "track": manifest["track"],
                "target": manifest["target"],
                "status": manifest["status"],
                "reason": manifest.get("reason") or manifest.get("error") or "",
                "CP": metric["CP"] if metric else None,
                "GS_generated": metric["GS_generated"] if metric else None,
                "GS_reference": metric["GS_reference"] if metric else None,
                "GS_absolute_difference": (
                    metric["GS_absolute_difference"] if metric else None
                ),
                "PCHE_generated": metric["PCHE_generated"] if metric else None,
                "PCHE_reference": metric["PCHE_reference"] if metric else None,
                "PCHE_absolute_difference": (
                    metric["PCHE_absolute_difference"] if metric else None
                ),
            }
        )

    max_pche = math.log2(12)
    for case in all_case_rows:
        if case["status"] != "completed":
            case["GS_match"] = None
            case["PCHE_match"] = None
            case["case_fit_score"] = None
            continue
        case["GS_match"] = 1 - case["GS_absolute_difference"]
        case["PCHE_match"] = (
            None
            if case["PCHE_absolute_difference"] is None
            else 1 - min(case["PCHE_absolute_difference"] / max_pche, 1.0)
        )
        components = [case["CP"], case["GS_match"]]
        if case["PCHE_match"] is not None:
            components.append(case["PCHE_match"])
        case["case_fit_score"] = statistics.fmean(components)
    write_csv(output_dir / "metrics_all_cases.csv", all_case_rows)

    case_lines = [
        "# Metrics by track and target",
        "",
        "Higher CP and GS are better. Lower PCHE absolute difference is better.",
        "PCHE is not applicable to drums.",
        "",
        "| Track | Target | Status | CP | GS | PCHE abs. diff. | Fit proxy |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for case in all_case_rows:
        if case["status"] == "completed":
            cp = f"{case['CP']:.6f}"
            gs = f"{case['GS_generated']:.6f}"
            pche = (
                "N/A"
                if case["PCHE_absolute_difference"] is None
                else f"{case['PCHE_absolute_difference']:.6f}"
            )
            fit = f"{case['case_fit_score']:.6f}"
            status = "completed"
        else:
            cp = gs = pche = fit = "—"
            status = f"{case['status']}: {case['reason']}"
        case_lines.append(
            f"| {case['track']} | {case['target']} | {status} | {cp} | {gs} | {pche} | {fit} |"
        )
    (output_dir / "metrics_by_track.md").write_text(
        "\n".join(case_lines) + "\n", encoding="utf-8"
    )

    track_rows = []
    for track in sorted({case["track"] for case in all_case_rows}):
        cases = [case for case in all_case_rows if case["track"] == track]
        valid = [case for case in cases if case["status"] == "completed"]
        melodic = [case for case in valid if case["PCHE_match"] is not None]
        fit_scores = [case["case_fit_score"] for case in valid]
        track_rows.append(
            {
                "track": track,
                "completed_instruments": len(valid),
                "failed_instruments": sum(case["status"] == "failed" for case in cases),
                "skipped_instruments": sum(case["status"] == "skipped" for case in cases),
                "CP_mean": statistics.fmean(case["CP"] for case in valid) if valid else None,
                "GS_match_mean": statistics.fmean(case["GS_match"] for case in valid) if valid else None,
                "PCHE_match_mean": (
                    statistics.fmean(case["PCHE_match"] for case in melodic)
                    if melodic
                    else None
                ),
                "quality_mean_completed": statistics.fmean(fit_scores) if fit_scores else None,
                "coverage_adjusted_score": sum(fit_scores) / 4,
            }
        )
    ranked = sorted(
        track_rows,
        key=lambda row: (
            row["coverage_adjusted_score"],
            row["quality_mean_completed"] if row["quality_mean_completed"] is not None else -1,
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    ranked_fields = ["rank", *[key for key in track_rows[0] if key != "rank"]]
    with (output_dir / "track_level_ranking.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=ranked_fields)
        writer.writeheader()
        writer.writerows(ranked)

    ranking_lines = [
        "# Track-level generation ranking",
        "",
        "This is a derived screening score, not an original MIDI-RWKV paper metric.",
        "",
        "- CP is used directly (higher is better).",
        "- GS match = 1 - absolute difference between generated and reference GS.",
        "- PCHE match = 1 - PCHE absolute difference / log2(12).",
        "- Per-instrument fit is the equal-weight mean of available components.",
        "- Quality mean uses completed instruments only.",
        "- Coverage-adjusted score divides the sum by four; failed and skipped instruments receive zero.",
        "",
        "| Rank | Track | Generated | CP mean | GS match | PCHE match | Quality (completed) | Coverage-adjusted |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in ranked:
        def display(value: float | None) -> str:
            return "N/A" if value is None else f"{value:.6f}"

        ranking_lines.append(
            f"| {row['rank']} | {row['track']} | {row['completed_instruments']}/4 | "
            f"{display(row['CP_mean'])} | {display(row['GS_match_mean'])} | "
            f"{display(row['PCHE_match_mean'])} | {display(row['quality_mean_completed'])} | "
            f"{row['coverage_adjusted_score']:.6f} |"
        )
    (output_dir / "track_level_ranking.md").write_text(
        "\n".join(ranking_lines) + "\n", encoding="utf-8"
    )

    summary["derived_track_ranking"] = {
        "warning": "Screening proxy, not an original MIDI-RWKV paper metric",
        "PCHE_normalization_denominator": max_pche,
        "ranking_basis": "coverage_adjusted_score",
        "tracks": ranked,
    }

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# MIDI-RWKV BabySlakh evaluation",
        "",
        f"Evaluated completed cases: **{len(rows)}**",
        "",
        "| Group | N | CP mean +/- std | GS mean +/- std | PCHE abs. diff. mean +/- std |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, values in [("Overall", summary["overall"]), *by_target.items()]:
        cp_stats = values["CP"]
        gs_stats = values["GS_generated"]
        pche_stats = values["PCHE_absolute_difference"]
        pche = (
            "N/A"
            if not pche_stats["count"]
            else f"{pche_stats['mean']:.5f} +/- {pche_stats['std']:.5f} (n={pche_stats['count']})"
        )
        lines.append(
            f"| {label} | {values['case_count']} | {cp_stats['mean']:.5f} +/- {cp_stats['std']:.5f} | "
            f"{gs_stats['mean']:.5f} +/- {gs_stats['std']:.5f} | {pche} |"
        )
    lines.extend(
        [
            "",
            "CP and GS follow the official MIDI-RWKV MIDIMetrics formulas. PCHE is the absolute entropy difference from the reference and is not computed for drums.",
            "",
            "Case-level values are in `metrics_per_case.csv`; full statistics and exclusions are in `summary.json`.",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
