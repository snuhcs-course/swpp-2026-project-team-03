#!/usr/bin/env python3
# AI-generated with Claude Code, 2026-10-31
"""Transcribe audio to MIDI with MuScriptor and report progress while it runs.

Writes the same MIDI as
  muscriptor transcribe AUDIO --model MODEL --device DEVICE \
      --format midi --detect-tempo false --output OUT.mid
(the call audio_to_midi.sh makes), but also reports progress. MuScriptor
splits the audio into 5-second chunks and its Python API emits a
ProgressEvent each time a chunk finishes; the CLI drops those events when it
writes MIDI, so this script calls the API directly.

Each progress update is one JSON line, appended to --progress (if given) and
printed to stderr:
  {"stage": "transcribe", "completed": 12, "total": 30, "fraction": 0.4,
   "elapsed_sec": 61.8, "eta_sec": 92.7}
eta_sec is null until the first chunk has finished.

Run with:
  uvx --python 3.13 --from muscriptor==0.4.0 python transcribe_with_progress.py \
      AUDIO OUT.mid --model large --progress progress.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from muscriptor.events import ProgressEvent
from muscriptor.transcription_model import TranscriptionModel
from muscriptor.utils.midi import ExportOptions


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output", type=Path, help="MIDI file to write")
    parser.add_argument("--model", default="large", help="small | medium | large | path to a .safetensors file")
    parser.add_argument("--device", default="auto", help="auto | cpu | cuda | mps")
    parser.add_argument("--instruments", help="comma-separated MuScriptor instrument hints for a stem")
    parser.add_argument("--progress", type=Path, help="append progress as JSON lines to this file")
    args = parser.parse_args()
    instruments = [name.strip() for name in args.instruments.split(",") if name.strip()] if args.instruments else None

    progress_file = args.progress.open("a", buffering=1) if args.progress else None

    def report(completed: int, total: int, started: float):
        elapsed = time.perf_counter() - started
        # Chunks take about the same time each, so the average so far predicts the rest.
        eta = elapsed / completed * (total - completed) if completed else None
        line = json.dumps({
            "stage": "transcribe",
            "completed": completed,
            "total": total,
            "fraction": round(completed / total, 4) if total else 1.0,
            "elapsed_sec": round(elapsed, 1),
            "eta_sec": None if eta is None else round(eta, 1),
        })
        print(line, file=sys.stderr, flush=True)
        if progress_file:
            progress_file.write(line + "\n")

    print("Loading model…", file=sys.stderr, flush=True)
    model = TranscriptionModel.load_model(
        weights_path=args.model, device=None if args.device == "auto" else args.device, dtype=None,
    )

    # Same arguments the CLI passes with its defaults. Progress events stay in
    # the list, as they do inside transcribe_and_postprocess.
    events = []
    started = time.perf_counter()
    for event in model.transcribe(
        args.audio, use_sampling=False, temperature=1.0, cfg_coef=1.0, instruments=instruments,
        batch_size=None, no_eos_is_ok=True, beam_size=1, prelude_forcing=True,
    ):
        events.append(event)
        if isinstance(event, ProgressEvent):
            if event.completed == 0:
                started = time.perf_counter()   # model warm-up and audio loading are done
            report(event.completed, event.total, started)

    # --detect-tempo false means no beat grid, and the CLI's export defaults
    # are ExportOptions()'s defaults.
    midi = model.events_to_midi_bytes(iter(events), beat_grid=None, export=ExportOptions())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(midi)
    print(f"Saved MIDI to {args.output}", file=sys.stderr, flush=True)
    if progress_file:
        progress_file.close()


if __name__ == "__main__":
    main()
