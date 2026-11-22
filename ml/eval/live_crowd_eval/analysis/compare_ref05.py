#!/usr/bin/env python3
"""05 원곡 비교: 버스킹(P04)의 MR = 원곡(B13) 반주. 원곡 베이스 채보를 기준으로 A·C 베이스 채보가 맞는지 센다.
P04 시각 = B13 시각 - 10.56초 (chroma 정렬로 측정). 기준도 채보 결과라 완벽한 정답은 아님(깨끗한 스튜디오 음원 채보).
사용: python3 analysis/compare_ref05.py  (out/R/B13 필요)"""
from pathlib import Path
import numpy as np, pretty_midi, mir_eval, warnings
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; OFF = -10.56
def notes(p, shift=0.0):
    m = pretty_midi.PrettyMIDI(str(p)); return [(n.start + shift, n.end + shift, n.pitch) for i in m.instruments for n in i.notes]
ref = notes(ROOT / "out/R/B13/stem_midi_gated/bass.mid", OFF)
est = {a: notes(ROOT / f"out/{a}/P04/stem_midi_gated/bass.mid") for a in ("A", "C")}
dur = 266.8
def score(r, e, t0, t1, pc=False):
    r = [x for x in r if t0 <= x[0] < t1]; e = [x for x in e if t0 <= x[0] < t1]
    if not r or not e: return dict(ref=len(r), est=len(e), match=0, precision=0.0 if e else None, recall=0.0 if r else None)
    f = (lambda p: 440.0 * 2 ** (((p % 12) + 60 - 69) / 12)) if pc else (lambda p: 440.0 * 2 ** ((p - 69) / 12))
    ri = np.array([[a, max(b, a + .01)] for a, b, _ in r]); ei = np.array([[a, max(b, a + .01)] for a, b, _ in e])
    m = len(mir_eval.transcription.match_notes(ri, np.array([f(p) for *_, p in r]), ei, np.array([f(p) for *_, p in e]), onset_tolerance=0.05, offset_ratio=None))
    return dict(ref=len(r), est=len(e), match=m, precision=round(m / len(e), 3), recall=round(m / len(r), 3))
for name, (t0, t1) in {"판정 05 구간 185~215초": (185, 215), "곡 전체 (0~266초)": (0, dur)}.items():
    print(f"\n[{name}]")
    for a in ("A", "C"):
        s = score(ref, est[a], t0, t1); s2 = score(ref, est[a], t0, t1, pc=True)
        print(f"  {a}: 기준 {s['ref']}개 / 채보 {s['est']}개 / 일치 {s['match']} → 정밀도 {s['precision']} 재현율 {s['recall']}"
              f"  (옥타브 무시: 일치 {s2['match']}, 정밀도 {s2['precision']})")
