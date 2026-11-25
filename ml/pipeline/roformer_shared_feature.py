#!/usr/bin/env python3
"""Extract the 512-D RoFormer shared-latent guitar feature for one song.

This extra GPU pass is separate from stem separation.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
import soundfile as sf

from separate_bs_roformer import MODEL_BASENAME, MODEL_DIRECTORY, verify_model, write_input_wav


class SharedPool:
    def __init__(self, bands: int):
        self.bands = bands
        self.total = self.square = None
        self.count = 0

    def hook(self, _module, inputs, mask):
        import torch
        x = inputs[0].detach().float()
        if x.ndim != 4 or x.shape[2] != self.bands or mask.ndim != 3:
            raise ValueError("RoFormer guitar mask-head feature shape changed")
        value = x.sum(dim=(0, 1, 2)).cpu().numpy().astype(np.float64)
        square = x.square().sum(dim=(0, 1, 2)).cpu().numpy().astype(np.float64)
        if self.total is None:
            self.total, self.square = value, square
        else:
            self.total += value
            self.square += square
        self.count += x.shape[0] * x.shape[1] * x.shape[2]

    def feature(self) -> np.ndarray:
        if not self.count:
            raise ValueError("No RoFormer chunks captured")
        mean = self.total / self.count
        std = np.sqrt(np.maximum(0, self.square / self.count - mean**2))
        result = np.concatenate((mean, std)).astype(np.float32)
        if result.shape != (512,) or not np.isfinite(result).all():
            raise ValueError("Invalid RoFormer shared-latent feature")
        return result


def extract(audio: Path, models_dir: Path, lib_dir: Path) -> np.ndarray:
    import torch
    import torch.nn.functional as F
    import yaml

    verify_model(models_dir)
    # ml_collections and bs_roformer both live in the BS-RoFormer package directory, not the venv
    # (separate_bs_roformer.py passes it as PYTHONPATH), so add it before importing either.
    sys.path.insert(0, str(lib_dir))
    from ml_collections import ConfigDict
    from bs_roformer.inference import SafeLoaderWithTuple
    from bs_roformer.utils import get_model_from_config

    model_dir = models_dir / MODEL_DIRECTORY
    with (model_dir / f"{MODEL_BASENAME}.yaml").open(encoding="utf-8") as handle:
        config = ConfigDict(yaml.load(handle, Loader=SafeLoaderWithTuple))
    instruments = list(config.training.instruments)
    model = get_model_from_config("bs_roformer", config)
    model.load_state_dict(torch.load(model_dir / f"{MODEL_BASENAME}.ckpt", map_location="cpu"))
    model = model.cuda().eval()
    guitar_head = model.mask_estimators[instruments.index("guitar")]
    with tempfile.TemporaryDirectory(prefix="roformer-shared-") as temporary:
        wav = Path(temporary) / "song.wav"
        write_input_wav(audio, wav)
        mix, _ = sf.read(wav, dtype="float32", always_2d=True)
    wave = torch.from_numpy(mix.T.copy())
    chunk_size = int(config.inference.chunk_size)
    step = chunk_size // int(config.inference.num_overlap)
    border = chunk_size - step
    if wave.shape[1] > 2 * border and border > 0:
        wave = F.pad(wave, (border, border), mode="reflect")
    pool = SharedPool(len(guitar_head.dim_inputs))
    hook = guitar_head.register_forward_hook(pool.hook)
    try:
        wave = wave.cuda()
        with torch.inference_mode(), torch.cuda.amp.autocast():
            for position in range(0, wave.shape[1], step):
                part = wave[:, position:position + chunk_size]
                length = part.shape[-1]
                if length < chunk_size:
                    if length > chunk_size // 2 + 1:
                        part = F.pad(part, (0, chunk_size - length), mode="reflect")
                    else:
                        part = F.pad(part, (0, chunk_size - length), mode="constant", value=0)
                _ = model(part.unsqueeze(0))
        return pool.feature()
    finally:
        hook.remove()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--lib-dir", type=Path, required=True)
    args = parser.parse_args()
    feature = extract(args.audio.resolve(strict=True), args.models_dir.resolve(), args.lib_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    with temp.open("wb") as handle:
        np.savez_compressed(handle, feature=feature)
    os.replace(temp, args.output)


if __name__ == "__main__":
    main()
