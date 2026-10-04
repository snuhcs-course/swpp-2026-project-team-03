#!/usr/bin/env python3
"""Transcribe MulTTiPop segments with YourMT3+ (YPTF.MoE+Multi, noPS).

Run this from the root of a clone of the YourMT3 Hugging Face Space, which
holds the model code and checkpoints:

    git lfs install
    git clone https://huggingface.co/spaces/mimbres/YourMT3
    cd YourMT3 && pip install -r requirements.txt
    python /path/to/run_yourmt3.py AUDIO_DIR OUTPUT_DIR

Every AUDIO_DIR/<id>.wav becomes OUTPUT_DIR/<id>/yourmt3.mid.  The model
arguments are copied from the Space's app.py.  NOTE: written against that
code but not executed in this repository's environment; verify on first use.
"""
from __future__ import annotations

import argparse, os, shutil, sys, time
from pathlib import Path

sys.path.append(os.path.abspath("amt/src"))

import torch
import torchaudio
from model_helper import load_model_checkpoint, transcribe  # from the Space root

CHECKPOINT = "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops@last.ckpt"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    precision = "16" if device == "cuda" else "32"
    model = load_model_checkpoint(device="cpu", args=[
        CHECKPOINT, "-p", "2024", "-tk", "mc13_full_plus_256", "-dec", "multi-t5",
        "-nl", "26", "-enc", "perceiver-tf", "-sqr", "1", "-ff", "moe",
        "-wf", "4", "-nmoe", "8", "-kmoe", "2", "-act", "silu", "-epe", "rope",
        "-rp", "1", "-ac", "spec", "-hop", "300", "-atc", "1", "-pr", precision])
    model.to(device)

    for audio in sorted(args.audio_dir.glob("*.wav")):
        info = torchaudio.info(str(audio))
        started = time.time()
        midi = transcribe(model, {
            "filepath": str(audio), "track_name": audio.stem,
            "sample_rate": int(info.sample_rate), "bits_per_sample": int(info.bits_per_sample),
            "num_channels": int(info.num_channels), "num_frames": int(info.num_frames),
            "duration": int(info.num_frames / info.sample_rate), "encoding": str.lower(info.encoding)})
        target = args.output_dir / audio.stem / "yourmt3.mid"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(midi, target)
        print(f"{audio.stem}: {time.time() - started:.1f}s on {device} -> {target}")


if __name__ == "__main__":
    main()
