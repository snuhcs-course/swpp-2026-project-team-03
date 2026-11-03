#!/usr/bin/env python3
"""Separate one song with the fixed BS-RoFormer SW six-stem checkpoint.

The inference package writes song_<stem>.wav plus song_instrumental.wav. This
adapter writes the seven files expected by unified.py: six canonical stems and
no_vocals.wav (all five non-vocal stems summed, scaled below full scale).
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf


STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")
NONVOCAL_STEMS = tuple(name for name in STEMS if name != "vocals")
MODEL_DIRECTORY = "roformer-model-bs-roformer-sw-by-jarredou"
MODEL_BASENAME = "BS-Rofo-SW-Fixed"
CHECKPOINT_SHA256 = "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e"
CONFIG_SHA256 = "52df622c95ff3c1f4e1389f476ed737581a2c2dc12324d52c9763be9ccd2be2b"
PACKAGE_VERSION = "bs-roformer-infer==0.1.5"
BLOCK_FRAMES = 65536


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def verify_model(models_dir: Path) -> None:
    model = models_dir / MODEL_DIRECTORY
    for path, expected in ((model / f"{MODEL_BASENAME}.ckpt", CHECKPOINT_SHA256),
                           (model / f"{MODEL_BASENAME}.yaml", CONFIG_SHA256)):
        if not path.is_file():
            raise FileNotFoundError(f"BS-RoFormer SW model asset missing: {path}")
        actual = digest(path)
        if actual != expected:
            raise ValueError(f"BS-RoFormer SW model asset checksum mismatch: {path} ({actual})")


def write_input_wav(source: Path, target: Path) -> None:
    """Give inference a safe fixed filename and a stereo float WAV."""
    try:
        with sf.SoundFile(str(source)) as audio:
            if audio.channels not in (1, 2):
                raise ValueError(f"Expected mono or stereo input, got {audio.channels} channels: {source}")
            with sf.SoundFile(str(target), mode="w", samplerate=audio.samplerate,
                              channels=2, subtype="FLOAT") as output:
                while True:
                    block = audio.read(BLOCK_FRAMES, dtype="float32", always_2d=True)
                    if not len(block):
                        break
                    output.write(np.repeat(block, 2, axis=1) if audio.channels == 1 else block)
    except RuntimeError as exc:
        raise ValueError(f"Cannot decode input audio as WAV/MP3/FLAC; convert it to WAV first: {source}") from exc


def mix_blocks(sources: dict[str, Path], frames: int):
    with ExitStack() as stack:
        stems = [stack.enter_context(sf.SoundFile(str(sources[name]))) for name in NONVOCAL_STEMS]
        remaining = frames
        while remaining:
            count = min(BLOCK_FRAMES, remaining)
            mix = np.zeros((count, 2), dtype="float32")
            for stem in stems:
                mix += stem.read(count, dtype="float32", always_2d=True)
            yield mix
            remaining -= count


def normalize_stems(raw_dir: Path, target_dir: Path) -> tuple[int, int, float]:
    sources = {name: raw_dir / f"song_{name}.wav" for name in STEMS}
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"BS-RoFormer did not produce all six stems: {missing}")
    infos = {name: sf.info(str(path)) for name, path in sources.items()}
    rates = {info.samplerate for info in infos.values()}
    channels = {info.channels for info in infos.values()}
    if len(rates) != 1 or channels != {2} or any(info.frames == 0 for info in infos.values()):
        raise ValueError("BS-RoFormer stems must be nonempty stereo WAVs with one sample rate")
    rate = rates.pop()
    frames = min(info.frames for info in infos.values())
    if max(info.frames for info in infos.values()) - frames > rate:
        raise ValueError("BS-RoFormer stem lengths differ by more than one second")

    target_dir.mkdir(parents=True, exist_ok=True)
    peak = 0.0
    for mix in mix_blocks(sources, frames):
        block_peak = float(np.max(np.abs(mix)))
        if not np.isfinite(block_peak):
            raise ValueError("BS-RoFormer produced a non-finite audio sample")
        peak = max(peak, block_peak)

    no_vocals = target_dir / "no_vocals.wav"
    scale = min(1.0, 0.99 / peak) if peak else 1.0
    with sf.SoundFile(str(no_vocals), mode="w", samplerate=rate,
                      channels=2, subtype="FLOAT") as output:
        for mix in mix_blocks(sources, frames):
            output.write(mix * scale)
    for name, source in sources.items():
        source.replace(target_dir / f"{name}.wav")
    return rate, frames, peak


def valid_stems(directory: Path) -> bool:
    try:
        infos = {name: sf.info(str(directory / f"{name}.wav")) for name in (*STEMS, "no_vocals")}
        return (len({info.samplerate for info in infos.values()}) == 1
                and {info.channels for info in infos.values()} == {2}
                and all(info.frames > 0 for info in infos.values())
                and infos["no_vocals"].frames == min(infos[name].frames for name in STEMS))
    except (OSError, RuntimeError, ValueError):
        return False


def separate(audio: Path, output_dir: Path, models_dir: Path, lib_dir: Path) -> None:
    verify_model(models_dir)
    if not lib_dir.is_dir():
        raise FileNotFoundError(f"BS-RoFormer package directory missing: {lib_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bsrofo-", dir=output_dir) as temporary:
        work = Path(temporary)
        input_dir, raw_dir, normalized = (work / name for name in ("input", "raw", "normalized"))
        input_dir.mkdir()
        raw_dir.mkdir()
        write_input_wav(audio, input_dir / "song.wav")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(lib_dir) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        subprocess.run([sys.executable, "-m", "bs_roformer.inference",
                        "--input_folder", str(input_dir), "--store_dir", str(raw_dir),
                        "--models_dir", str(models_dir)], env=env, check=True)
        rate, frames, peak = normalize_stems(raw_dir, normalized)
        for name in (*STEMS, "no_vocals"):
            (normalized / f"{name}.wav").replace(output_dir / f"{name}.wav")
    if not valid_stems(output_dir):
        raise ValueError(f"Invalid normalized BS-RoFormer stem set: {output_dir}")
    print(f"BS-RoFormer SW: {rate} Hz, {frames} frames, no_vocals peak before scaling {peak:.3f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--models-dir", type=Path, default=Path("/data/bsrofo/models"))
    parser.add_argument("--lib-dir", type=Path, default=Path("/data/bsrofo/pylib"))
    args = parser.parse_args()
    separate(args.audio.resolve(strict=True), args.output_dir.resolve(),
             args.models_dir.resolve(), args.lib_dir.resolve())


if __name__ == "__main__":
    main()
