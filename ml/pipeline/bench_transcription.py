#!/usr/bin/env python3
"""Compare MuScriptor stem concurrency against saved single-process MIDI outputs.

Example:
  python bench_transcription.py RUN/stem_midi/transcription_jobs.json OUT \
      --model /data/model/model.safetensors --workers 2 4
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu_memory_peak(stop: threading.Event, values: list[int]) -> None:
    while not stop.wait(0.5):
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                                     "--format=csv,noheader,nounits"],
                                    capture_output=True, text=True, check=True)
            values.extend(int(value.strip()) for value in result.stdout.splitlines())
        except (OSError, ValueError, subprocess.CalledProcessError):
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs_file", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--model", default="/data/model/model.safetensors")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--workers", type=int, nargs="+", default=[2, 4])
    args = parser.parse_args()
    jobs = json.loads(args.jobs_file.read_text(encoding="utf-8"))
    priority = {"guitar": 0, "bass": 1, "piano": 2, "drums": 3}
    jobs.sort(key=lambda job: priority[job["stem"]])
    if not jobs or not all(1 <= count <= len(jobs) for count in args.workers):
        parser.error("worker counts must be between 1 and the number of stems")
    if args.output_dir.exists():
        parser.error("output_dir already exists; use a new directory for each benchmark")
    args.output_dir.mkdir(parents=True)
    summary = []

    for workers in args.workers:
        out = args.output_dir / f"workers_{workers}"
        out.mkdir()
        stop = threading.Event()
        gpu_samples: list[int] = []
        monitor = threading.Thread(target=gpu_memory_peak, args=(stop, gpu_samples), daemon=True)
        monitor.start()

        def run(job: dict) -> dict:
            stem = job["stem"]
            midi = out / f"{stem}.mid"
            command = [sys.executable, str(Path(__file__).with_name("transcribe_with_progress.py")),
                       job["audio"], str(midi), "--model", args.model, "--device", args.device,
                       "--instruments", job["instruments"], "--progress", str(out / f"{stem}.progress.jsonl")]
            started = time.perf_counter()
            with (out / f"{stem}.log").open("w", encoding="utf-8") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            return {"stem": stem, "seconds": round(time.perf_counter() - started, 2),
                    "sha256": sha256(midi), "matches_reference": sha256(midi) == sha256(Path(job["output"]))}

        started = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                tracks = list(pool.map(run, jobs))
        finally:
            stop.set()
            monitor.join(timeout=2)
        result = {"workers": workers, "seconds": round(time.perf_counter() - started, 2),
                  "peak_gpu_memory_mib": max(gpu_samples, default=None), "tracks": tracks}
        summary.append(result)
        (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
        if not all(track["matches_reference"] for track in tracks):
            raise RuntimeError("Parallel transcription changed a stem MIDI output")


if __name__ == "__main__":
    main()
