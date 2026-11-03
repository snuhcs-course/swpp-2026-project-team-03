"""Separate one song into drums/bass/guitar/piano/other/vocals WAVs (run with /data/envs/sep/bin/python).

    python sep.py demucs|bsrofo INPUT.wav OUT_DIR

demucs: htdemucs_6s exactly as ml/pipeline/separate_stems.py (shifts=1, split, overlap 0.25, CLI normalisation)
bsrofo: BS-RoFormer SW 6-stem (bs-roformer-infer 0.1.5), weights in /data/models/bsrofo

Written with Claude (AI); experiment script for the separation comparison, not part of the app pipeline.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf
import torch

STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")


def demucs(src, out):
    from demucs.apply import apply_model
    from demucs.audio import convert_audio
    from demucs.pretrained import get_model
    model = get_model("htdemucs_6s").eval()
    audio, rate = sf.read(str(src), dtype="float32", always_2d=True)
    wave = convert_audio(torch.from_numpy(audio.T), rate, model.samplerate, model.audio_channels)
    ref = wave.mean(0)
    wave = (wave - ref.mean()) / ref.std()
    with torch.no_grad():
        stems = apply_model(model, wave[None], device="cuda", shifts=1, split=True, overlap=0.25)[0]
    stems = stems * ref.std() + ref.mean()
    for name, stem in zip(model.sources, stems):
        sf.write(str(out / f"{name}.wav"), stem.cpu().numpy().T, model.samplerate)


def bsrofo(src, out):
    with tempfile.TemporaryDirectory(dir=str(out)) as tmp:
        inp, res = Path(tmp) / "in", Path(tmp) / "out"
        inp.mkdir()
        (inp / "song.wav").symlink_to(Path(src).resolve())      # stems become song_<stem>.wav
        subprocess.run([sys.executable, "-m", "bs_roformer.inference", "--input_folder", str(inp),
                        "--store_dir", str(res), "--models_dir", "/data/models/bsrofo"], check=True)
        for name in STEMS:
            audio, rate = sf.read(str(res / f"song_{name}.wav"), dtype="float32", always_2d=True)
            sf.write(str(out / f"{name}.wav"), audio, rate)     # 16-bit, like the Demucs stems


if __name__ == "__main__":
    method, src, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    {"demucs": demucs, "bsrofo": bsrofo}[method](src, out)
    missing = [s for s in STEMS if not (out / f"{s}.wav").exists()]
    if missing:
        sys.exit(f"missing stems: {missing}")
    print(f"{method}: stems written to {out}")
