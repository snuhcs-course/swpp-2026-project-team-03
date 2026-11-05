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

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?", help="MIDI file to write")
    parser.add_argument("--jobs-file", type=Path, help="JSON list of stem/audio/output/hints/progress jobs")
    parser.add_argument("--resume-existing", action="store_true", help="skip valid MIDI outputs in a batch")
    parser.add_argument("--model", default="large", help="small | medium | large | path to a .safetensors file")
    parser.add_argument("--device", default="auto", help="auto | cpu | cuda | mps")
    parser.add_argument("--instruments", help="comma-separated MuScriptor instrument hints for a stem")
    parser.add_argument("--progress", type=Path, help="append progress as JSON lines to this file")
    args = parser.parse_args()
    if args.jobs_file:
        if args.audio or args.output or args.instruments or args.progress:
            parser.error("--jobs-file cannot be combined with single-stem arguments")
        jobs = json.loads(args.jobs_file.read_text(encoding="utf-8"))
        if not isinstance(jobs, list) or not jobs:
            parser.error("--jobs-file must contain a nonempty list")
    elif args.audio and args.output:
        jobs = [{"audio": str(args.audio), "output": str(args.output),
                 "instruments": args.instruments,
                 "progress": str(args.progress) if args.progress else None}]
    else:
        parser.error("provide AUDIO OUT.mid or --jobs-file")

    # Loading large once avoids four model initializations and GPU allocations.
    # Inference remains sequential so peak GPU memory stays near the old path.
    from muscriptor.events import ProgressEvent
    from muscriptor.transcription_model import TranscriptionModel
    from muscriptor.utils.midi import ExportOptions

    model = None
    for job in jobs:
        audio, output = Path(job["audio"]), Path(job["output"])
        progress = Path(job["progress"]) if job.get("progress") else None
        if args.resume_existing and output.is_file() and output.stat().st_size:
            try:
                import pretty_midi
                pretty_midi.PrettyMIDI(str(output))
            except (OSError, ValueError, EOFError):
                pass
            else:
                print(f"Skipping valid MIDI: {output}", file=sys.stderr, flush=True)
                continue
        if model is None:
            print("Loading model…", file=sys.stderr, flush=True)
            model = TranscriptionModel.load_model(
                weights_path=args.model, device=None if args.device == "auto" else args.device,
                dtype=None,
            )
        hints = job.get("instruments")
        instruments = [name.strip() for name in hints.split(",") if name.strip()] if hints else None
        if progress:
            progress.parent.mkdir(parents=True, exist_ok=True)
        progress_file = progress.open("a", buffering=1) if progress else None
        try:
            events = []
            started = time.perf_counter()
            for event in model.transcribe(
                audio, use_sampling=False, temperature=1.0, cfg_coef=1.0, instruments=instruments,
                batch_size=None, no_eos_is_ok=True, beam_size=1, prelude_forcing=True,
            ):
                events.append(event)
                if isinstance(event, ProgressEvent):
                    if event.completed == 0:
                        started = time.perf_counter()
                    elapsed = time.perf_counter() - started
                    eta = elapsed / event.completed * (event.total - event.completed) if event.completed else None
                    line = json.dumps({
                        "stage": "transcribe", "completed": event.completed, "total": event.total,
                        "fraction": round(event.completed / event.total, 4) if event.total else 1.0,
                        "elapsed_sec": round(elapsed, 1),
                        "eta_sec": None if eta is None else round(eta, 1),
                    })
                    print(line, file=sys.stderr, flush=True)
                    if progress_file:
                        progress_file.write(line + "\n")
            midi = model.events_to_midi_bytes(iter(events), beat_grid=None, export=ExportOptions())
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(midi)
            print(f"Saved MIDI to {output}", file=sys.stderr, flush=True)
        finally:
            if progress_file:
                progress_file.close()


if __name__ == "__main__":
    main()
