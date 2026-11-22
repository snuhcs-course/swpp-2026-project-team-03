#!/usr/bin/env python3
"""cleaned2 = 원본 - crowd stem (직접 계산, 음량 정규화 없음). 기존 cleaned의 음량 변화도 기록.
사용: python make_clean2.py /data/live_eval  → crowd/cleaned2/<id>.wav, crowd/clean2_check.csv"""
import csv, os, sys
from pathlib import Path
import numpy as np, soundfile as sf
E = Path(sys.argv[1]); ids = [l.strip() for l in open(E / "pipeline_ids.txt") if l.strip()]
out = E / "crowd" / "cleaned2"; out.mkdir(parents=True, exist_ok=True)
rows = []
for i in ids:
    mix, sr = sf.read(E / "wav" / f"{i}.wav", always_2d=True)
    crowd, _ = sf.read(E / "crowd" / "crowd" / f"{i}.flac", always_2d=True)
    old, _ = sf.read(E / "crowd" / "cleaned" / f"{i}.wav", always_2d=True)
    n = len(mix); crowd = crowd[:n]; old = old[:n]
    c2 = mix - crowd
    part = out / f".{i}.part.wav"
    sf.write(part, c2.astype(np.float32), sr, subtype="FLOAT"); os.replace(part, out / f"{i}.wav")  # 32-bit float: 1.0을 넘어도 잘리지 않음
    gain = float(np.sum(c2 * old) / max(np.sum(old * old), 1e-12))  # 기존 cleaned가 몇 배 작아졌는지
    rows.append(dict(id=i, old_cleaned_gain=round(gain, 4), old_cleaned_level_db=round(-20 * np.log10(gain), 2),
                     crowd_peak=round(float(np.abs(crowd).max()), 3), clean2_peak=round(float(np.abs(c2).max()), 3),
                     over_1_samples=int((np.abs(c2) > 1).sum())))
    print(rows[-1], flush=True)
with open(E / "crowd" / "clean2_check.csv", "w", newline="") as fp:
    w = csv.DictWriter(fp, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
