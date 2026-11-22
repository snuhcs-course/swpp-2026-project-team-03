#!/usr/bin/env python3
"""곡별 관중 구간·음악 구간 초 목록 (crowd_segments.py와 같은 기준). 사용: python crowd_secs.py /data/live_eval > crowd_secs.json"""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf
E = Path(sys.argv[1]); ids = [l.strip() for l in open(E / "pipeline_ids.txt") if l.strip()]
out = {}
for sid in ids:
    mix, sr = sf.read(E / "wav" / f"{sid}.wav", always_2d=True)
    cr, _ = sf.read(E / "crowd" / "crowd" / f"{sid}.flac", always_2d=True)
    n = min(len(mix), len(cr)); mix, cr = mix[:n], cr[:n]; secs = n // sr
    e = lambda x: np.mean(x[: secs * sr].reshape(secs, sr, 2) ** 2, axis=(1, 2)) + 1e-12
    rel = 10 * np.log10(e(cr) / e(mix - cr)); loud = 10 * np.log10(e(mix)) > -60
    out[sid] = {"crowd": [int(s) for s in np.where(loud & (rel >= 6))[0]],
                "music": [int(s) for s in np.where(loud & (rel <= -20))[0]], "secs": int(secs)}
json.dump(out, sys.stdout)
