#!/usr/bin/env python3
"""Index the MulTTiPop dataset and write the audio manifest for the test picks.

Writes two CSV files next to this script:
  samples.csv         every segment with its reference MIDI path, YouTube id,
                      time range, song metadata, and note counts per family
  audio_manifest.csv  the segments listed in candidates.txt, with the YouTube
                      URL, time range, and the path the audio must be saved to
"""
from __future__ import annotations

import argparse, csv, json, warnings
from pathlib import Path

import pretty_midi

from collapse_midi import FAMILY_ORDER, collapse

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
AUDIO_DIR = Path("data/audio/multtipop")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/datasets/multtipop")
    parser.add_argument("--candidates", type=Path, default=HERE / "candidates.txt")
    args = parser.parse_args()
    warnings.filterwarnings("ignore")

    rows = []
    for split in ("dev", "test"):
        # genre is only present in the split-level JSON, not in meta.json
        for item in json.loads((args.dataset / f"{split}.json").read_text()):
            midi_path = args.dataset / split / item["id"] / "aligned.mid"
            _, report = collapse(pretty_midi.PrettyMIDI(str(midi_path)), drop_vocal_tracks=True)
            notes, youtube = report["notes"], item["youtube"]
            rows.append({
                "id": item["id"], "split": split, "artist": item["artist"], "name": item["name"],
                "year": item["year"], "genre": item.get("genre_everynoise") or "", "section": item["section"],
                "reference_midi": midi_path.relative_to(PROJECT_ROOT).as_posix(),
                "youtube_id": youtube["ytid"],
                "start_sec": f"{youtube['start']:.3f}", "end_sec": f"{youtube['end']:.3f}",
                "duration_sec": f"{youtube['end'] - youtube['start']:.3f}",
                **{f"notes_{name}": notes[name] for name in [*FAMILY_ORDER, "vocal", "other"]},
                "families_present": sum(notes[name] > 0 for name in FAMILY_ORDER),
            })
    write_csv(HERE / "samples.csv", rows)

    by_id = {row["id"]: row for row in rows}
    wanted = [line.split("#")[0].strip() for line in args.candidates.read_text().splitlines()]
    manifest = []
    for sample_id in filter(None, wanted):
        row = by_id[sample_id]
        manifest.append({
            **{key: row[key] for key in ("id", "split", "artist", "name", "year", "section")},
            "youtube_url": f"https://www.youtube.com/watch?v={row['youtube_id']}",
            "youtube_id": row["youtube_id"],
            # a few segments start slightly before 0; audio cannot, so clamp
            "start_sec": f"{max(0.0, float(row['start_sec'])):.3f}", "end_sec": row["end_sec"],
            "duration_sec": row["duration_sec"],
            "audio_path": (AUDIO_DIR / f"{sample_id}.wav").as_posix(),
            "reference_midi": row["reference_midi"],
        })
    write_csv(HERE / "audio_manifest.csv", manifest)


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
