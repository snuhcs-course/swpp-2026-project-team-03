#!/usr/bin/env python3
# AI-generated with Claude Code, 2026-10-13
"""Split an audio file into stems with Demucs.

Writes OUTPUT_DIR/<stem>.wav for every stem of the model.  htdemucs gives
drums, bass, other, and vocals.  htdemucs_6s adds guitar and piano; its
authors call it experimental and warn that the piano stem is weak.

Run with:
  uvx --python 3.11 --with demucs --with soundfile --with "torch<2.6" \
      --with "torchaudio<2.6" python separate_stems.py INPUT.wav OUTPUT_DIR
(torch 2.6+ refuses to load the published Demucs checkpoints.)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.audio import convert_audio
from demucs.pretrained import get_model


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--no-vocals-mix", action="store_true",
                        help="also write no_vocals.wav, the sum of every stem except vocals")
    args = parser.parse_args()

    model = get_model(args.model).eval()
    # not MPS: htdemucs hits "Output channels > 65536 not supported at the MPS device"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    audio, rate = sf.read(str(args.input), dtype="float32", always_2d=True)
    wave = convert_audio(torch.from_numpy(audio.T), rate, model.samplerate, model.audio_channels)
    # normalise the way the Demucs CLI does, then undo it on the stems
    reference = wave.mean(0)
    wave = (wave - reference.mean()) / reference.std()
    with torch.no_grad():
        stems = apply_model(model, wave[None], device=device, shifts=1, split=True, overlap=0.25)[0]
    stems = stems * reference.std() + reference.mean()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, stem in zip(model.sources, stems):
        sf.write(str(args.output_dir / f"{name}.wav"), stem.cpu().numpy().T, model.samplerate)
        print(f"{name:8} rms {stem.pow(2).mean().sqrt().item():.4f}")

    if args.no_vocals_mix:
        mix = sum(stem for name, stem in zip(model.sources, stems) if name != "vocals")
        peak = mix.abs().max().item()
        if peak > 0.99:  # the summed stems can exceed full scale; scale down instead of clipping
            mix = mix * (0.99 / peak)
        sf.write(str(args.output_dir / "no_vocals.wav"), mix.cpu().numpy().T, model.samplerate)
        print(f"no_vocals peak {peak:.3f}")


if __name__ == "__main__":
    main()
