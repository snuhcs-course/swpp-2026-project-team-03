#!/usr/bin/env python3
"""관중만 나오는 구간의 '가짜 음' 세기 (클러스터 안에서 실행, 작은 CSV만 만듦).
1초 구간마다 crowd stem 에너지와 음악(원본 - crowd) 에너지를 비교해서
  crowd 구간 : crowd가 음악보다 6 dB 이상 큰 구간 (함성·박수만 들리는 곳)
  music 구간 : crowd가 음악보다 20 dB 이상 작은 구간 (관중 소리가 거의 없는 곳)
으로 나누고, 각 실행(A/B/C)의 악기별 채보 음표가 그 구간에 몇 개 있는지 센다.
crowd 구간에서 음표가 줄면 관중 소리 때문에 생긴 가짜 음이 사라졌다는 뜻이고,
music 구간에서는 크게 바뀌지 않아야 정상이다.
사용: python crowd_segments.py /data/live_eval  → /data/live_eval/crowd_segments.csv"""
import csv, sys
from pathlib import Path
import numpy as np, soundfile as sf, pretty_midi
E = Path(sys.argv[1]); ids = [l.strip() for l in open(E / "pipeline_ids.txt") if l.strip()]
INSTS = ["drums", "bass", "guitar", "piano"]
rows = []
for sid in ids:
    mix, sr = sf.read(E / "wav" / f"{sid}.wav", always_2d=True)
    crowd, _ = sf.read(E / "crowd" / "crowd" / f"{sid}.flac", always_2d=True)
    n = min(len(mix), len(crowd)); mix, crowd = mix[:n], crowd[:n]; music = mix - crowd
    secs = n // sr
    e = lambda x: np.mean(x[: secs * sr].reshape(secs, sr, 2) ** 2, axis=(1, 2)) + 1e-12
    ec, em, ex = e(crowd), e(music), e(mix)
    rel = 10 * np.log10(ec / em); loud = 10 * np.log10(ex) > -60
    seg = {"crowd": loud & (rel >= 6), "music": loud & (rel <= -20)}
    for arm in ("A", "B", "C"):
        d = E / "out" / arm / sid / "stem_midi_gated"
        if not d.exists(): continue
        for inst in INSTS:
            p = d / f"{inst}.mid"
            on = np.array([nt.start for i in pretty_midi.PrettyMIDI(str(p)).instruments for nt in i.notes]) if p.exists() else np.zeros(0)
            idx = np.clip(on.astype(int), 0, secs - 1) if len(on) else np.zeros(0, int)
            for name, mask in seg.items():
                rows.append(dict(id=sid, arm=arm, inst=inst, segment=name, seconds=int(mask.sum()),
                                 notes=int(mask[idx].sum()) if len(idx) else 0))
    print(sid, {k: int(v.sum()) for k, v in seg.items()}, flush=True)
with open(E / "crowd_segments.csv", "w", newline="") as fp:
    w = csv.DictWriter(fp, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("저장:", E / "crowd_segments.csv")
