#!/usr/bin/env python3
"""03·07 원곡 비교: 라이브와 원곡을 chroma DTW로 정렬해 원곡 기타 채보를 라이브 시간으로 옮기고, A·C 기타 채보와 비교.
라이브는 템포·편곡이 원곡과 달라 05(같은 MR)보다 약한 근거임."""
import sys, numpy as np, librosa, pretty_midi, mir_eval, warnings
warnings.filterwarnings("ignore")
SR, HOP = 22050, 2048; FPS = SR / HOP
CASES = [("03", "L04", "R01", "guitar", 175, 205), ("07", "P08", "B22", "guitar", 90, 120)]
def chroma(p):
    y, _ = librosa.load(p, sr=SR, mono=True)
    c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP); return c / (np.linalg.norm(c, axis=0, keepdims=True) + 1e-9)
def notes(p):
    m = pretty_midi.PrettyMIDI(p); return [(n.start, n.end, n.pitch) for i in m.instruments for n in i.notes]
def pc_hist(ns, t0, t1):
    h = np.zeros(12)
    for a, b, p in ns:
        ov = min(b, t1) - max(a, t0)
        if ov > 0: h[p % 12] += ov
    return h / (np.linalg.norm(h) + 1e-9)
def match(r, e, tol, pc):
    if not r or not e: return 0
    f = (lambda p: 440 * 2 ** (((p % 12) + 60 - 69) / 12)) if pc else (lambda p: 440 * 2 ** ((p - 69) / 12))
    ri = np.array([[a, max(b, a + .01)] for a, b, _ in r]); ei = np.array([[a, max(b, a + .01)] for a, b, _ in e])
    return len(mir_eval.transcription.match_notes(ri, np.array([f(p) for *_, p in r]), ei, np.array([f(p) for *_, p in e]), onset_tolerance=tol, offset_ratio=None))
for k, live, ref, inst, t0, t1 in CASES:
    cl, cr = chroma(f"wav/{live}.wav"), chroma(f"wav/{ref}.wav")
    D, wp = librosa.sequence.dtw(X=cl, Y=cr, metric="cosine", subseq=False)
    wp = wp[::-1]; lt, rt = wp[:, 0] / FPS, wp[:, 1] / FPS
    cost = float(np.mean([1 - cl[:, i] @ cr[:, j] for i, j in wp]))
    # 정렬 품질: 구간별 기울기(원곡 1초당 라이브 초)와 구간 내 평균 유사도
    inw = (lt >= t0) & (lt < t1)
    sims = np.array([cl[:, i] @ cr[:, j] for i, j in wp])
    slope = np.polyfit(rt[inw], lt[inw], 1)[0] if inw.sum() > 5 else float("nan")
    # 원곡 → 라이브 시간 변환 (단조 보간)
    ur, idx = np.unique(rt, return_index=True); to_live = lambda t: float(np.interp(t, ur, lt[idx]))
    rn = [(to_live(a), to_live(b), p) for a, b, p in notes(f"out/R/{ref}/stem_midi_gated/{inst}.mid")]
    r_w = [x for x in rn if t0 <= x[0] < t1]
    print(f"\n[{k} {live} ↔ 원곡 {ref} | 라이브 {t0}~{t1}초 | 전체 정렬 유사도 {1-cost:.3f}, 구간 유사도 {sims[inw].mean():.3f}, 구간 템포비 {slope:.3f}]")
    print(f"  원곡 기타 음(구간 안): {len(r_w)}개, 음높이 범위 {min(p for *_,p in r_w) if r_w else '-'}~{max(p for *_,p in r_w) if r_w else '-'}")
    hr = pc_hist(rn, t0, t1)
    for arm in ("A", "C"):
        e = [x for x in notes(f"out/{arm}/{live}/stem_midi_gated/{inst}.mid") if t0 <= x[0] < t1]
        m1, m2 = match(r_w, e, 0.1, False), match(r_w, e, 0.1, True)
        sim = float(hr @ pc_hist(e, t0, t1)) if e else 0.0
        print(f"  {arm}: 채보 {len(e)}개 | 음 일치(±100ms) {m1} → 정밀도 {m1/len(e) if e else 0:.3f} 재현율 {m1/len(r_w) if r_w else 0:.3f}"
              f" | 옥타브 무시 일치 {m2} → 정밀도 {m2/len(e) if e else 0:.3f} | 음높이 구성 유사도 {sim:.3f}")
