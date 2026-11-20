"""Pool MuScriptor final decoder logits during the existing guitar transcription."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch


class DecoderLogitsMoments:
    def __init__(self, dim: int):
        self.dim = dim
        self.total = None
        self.square = None
        self.count = 0

    def hook(self, _module, _inputs, value: torch.Tensor) -> None:
        if value.ndim != 3 or value.shape[0] != 1 or value.shape[2] != self.dim:
            raise ValueError("MuScriptor decoder logits shape changed")
        last = value[0, -1].detach().to(dtype=torch.float32)
        if self.total is None:
            self.total = torch.zeros_like(last)
            self.square = torch.zeros_like(last)
        self.total.add_(last)
        self.square.addcmul_(last, last)
        self.count += 1

    def save(self, path: Path) -> None:
        if not self.count:
            raise ValueError("No MuScriptor decoder steps captured")
        mean = self.total / self.count
        var = (self.square / self.count - mean.square()).clamp_min_(0)
        feature = torch.cat((mean, torch.sqrt(var))).cpu().numpy().astype(np.float32)
        if feature.shape != (2 * self.dim,) or not np.isfinite(feature).all():
            raise ValueError("Invalid MuScriptor decoder feature")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("wb") as handle:
            np.savez_compressed(handle, feature=feature)
        os.replace(temp, path)
