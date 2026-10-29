"""
생성 결과 평가 (원래 파트 vs 생성 파트) — MIDI-GPT / MIDI-RWKV 등 생성 모델 공통

입력 폴더 구조 (p12_step5_generate4.py 결과와 동일)
  <결과폴더>/TrackXXXXX/<악기>/answer_only.mid     원래 그 악기 파트 (여러 트랙이면 합쳐서 봄)
  <결과폴더>/TrackXXXXX/<악기>/generated_only.mid  생성된 그 악기 파트
  → 다른 모델 결과도 이 구조로만 저장하면 그대로 비교 가능

지표 (MIDI-RWKV 논문이 쓴 MIDIMetrics 코드의 정의를 따름)
  cp            Content Preservation: 마디당 16칸 음이름 분포(반 마디 이동평균)의 코사인 유사도 평균   ↑
  cp_active     위와 같되 원래 파트가 소리 내는 칸만 평균 (쉬는 구간 제외 참고값)                     ↑
  gs_orig/gen   Groove Consistency: 32분음표 격자에서 이웃 마디끼리 리듬 패턴이 얼마나 같은지          원래와 가까울수록
  gs_diff       |gs_orig - gs_gen|                                                                    ↓
  gs_match      같은 마디끼리 원래·생성의 음 시작 위치 일치율 (논문 본문 설명 방식, 참고값)          ↑
  pche_orig/gen Pitch Class Histogram Entropy: 음이름 분포의 엔트로피(조성감)                         원래와 가까울수록
  pche_diff     |pche_orig - pche_gen|                                                                ↓
  드럼은 음 높이 = 타악기 종류라 cp·pche·pch_sim은 계산하지 않음 (gs 중심으로 봄)

추가 지표
  pch_sim       Pitch-class histogram 코사인 유사도 (MGEval 계열)                                     ↑
  f1            음 단위 F1: 같은 음높이 + 시작 시점 차이 32분음표 이내 (생성에는 참고값)              ↑
  jaccard       16분음표 피아노롤 겹침 (MIDI-GPT 논문 7.1절, 원본 베끼기 확인용)
  연주 가능성·스타일 (원래/생성 각각): notes_per_bar, max_poly(동시 타건 최대), mean_poly,
                pitch_min/max/span, note_len(평균 음 길이, 박), ioi(음 시작 간격 평균, 박), empty_bars

사용법
  python eval_generation.py step5_out                 # 결과: eval_results.csv, eval_summary.csv
  python eval_generation.py step5_out rwkv_out        # 두 모델 결과를 한 번에 (모델명 = 폴더명)
필요: pip install "midigpt[inference]"  (MIDI 마디 구조를 읽는 데 사용)
"""
import csv
import math
import os
import sys
from collections import Counter

import midigpt
import numpy as np

INSTRUMENTS = ["piano", "guitar", "bass", "drums"]
CP_STEPS = 16        # 마디당 칸 수 (MIDIMetrics와 동일)
GS_PER_BEAT = 8      # 32분음표 격자 (MIDIMetrics: tpq // 8)
ROLL_PER_BEAT = 4    # Jaccard용 16분음표 격자


# ---------- MIDI → 마디별 음표 ----------
def load_bars(path):
    """반환: [(마디 길이(박), [(시작(박), 길이(박), 음높이), ...]), ...]  여러 트랙은 합침."""
    d = midigpt.Score.from_midi(path).to_dict()
    res = d["resolution"]
    if not d["tracks"]:
        return []
    n = max(len(t["bars"]) for t in d["tracks"])
    ref = max(d["tracks"], key=lambda t: len(t["bars"]))
    bars = []
    for i in range(n):
        b = ref["bars"][i]
        beats = 4 * b.get("ts_numerator", 4) / b.get("ts_denominator", 4)
        notes = []
        for t in d["tracks"]:
            if i < len(t["bars"]):
                for x in t["bars"][i]["notes"]:
                    notes.append((x["onset_ticks"] / res, max(x["duration_ticks"], 1) / res, x["pitch"]))
        bars.append((beats, notes))
    return bars


def flat(bars):
    """절대 위치(박)로 펼친 음표 목록"""
    out, start = [], 0.0
    for beats, notes in bars:
        out += [(start + s, l, p) for s, l, p in notes]
        start += beats
    return out


# ---------- MIDI-RWKV 지표 ----------
def chroma_frames(bars):
    frames = []
    for beats, notes in bars:
        step = beats / CP_STEPS
        for k in range(CP_STEPS):
            a, b = k * step, (k + 1) * step
            v = np.zeros(12)
            for s, l, p in notes:
                if s < b and s + l > a:
                    v[p % 12] += 1
            frames.append(v)
    m = np.array(frames)
    m = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-8)
    half = CP_STEPS // 2
    sm = np.array([m[max(0, i - half // 2): i + half // 2].mean(axis=0) if len(m[max(0, i - half // 2): i + half // 2])
                   else np.zeros(12) for i in range(len(m))])
    return sm, np.array([f.sum() > 0 for f in frames])


def cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0


def content_preservation(orig, gen):
    co, active = chroma_frames(orig)
    cg, _ = chroma_frames(gen)
    sims = [cos(co[i], cg[i]) for i in range(min(len(co), len(cg)))]
    act = [s for s, a in zip(sims, active) if a]
    return float(np.mean(sims)), (float(np.mean(act)) if act else float("nan"))


def onset_grid(bars, per_beat):
    rows = []
    width = max(int(round(b * per_beat)) for b, _ in bars)
    for beats, notes in bars:
        r = np.zeros(width, dtype=bool)
        for s, _, _ in notes:
            k = int(s * per_beat)
            if 0 <= k < width:
                r[k] = True
        rows.append(r)
    return np.array(rows)


def groove_consistency(bars):
    g = onset_grid(bars, GS_PER_BEAT)
    if len(g) < 2:
        return float("nan")
    hd = np.count_nonzero(g[:-1] != g[1:])
    return 1 - hd / (g.shape[1] * len(g))


def groove_match(orig, gen):
    go, gg = onset_grid(orig, GS_PER_BEAT), onset_grid(gen, GS_PER_BEAT)
    n = min(len(go), len(gg))
    w = min(go.shape[1], gg.shape[1])
    return float(np.mean([(go[i, :w] == gg[i, :w]).mean() for i in range(n)])) if n else float("nan")


def pc_hist(notes):
    h = np.zeros(12)
    for _, _, p in notes:
        h[p % 12] += 1
    return h


def entropy(h):
    if h.sum() == 0:
        return float("nan")
    p = h / h.sum()
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


# ---------- 추가 지표 ----------
def f1(orig_notes, gen_notes, tol=1 / GS_PER_BEAT):
    if not orig_notes or not gen_notes:
        return 0.0
    used, tp = set(), 0
    by_pitch = {}
    for i, (s, _, p) in enumerate(orig_notes):
        by_pitch.setdefault(p, []).append((s, i))
    for s, _, p in gen_notes:
        best = None
        for so, i in by_pitch.get(p, []):
            if i not in used and abs(so - s) <= tol and (best is None or abs(so - s) < abs(best[0] - s)):
                best = (so, i)
        if best:
            used.add(best[1])
            tp += 1
    prec, rec = tp / len(gen_notes), tp / len(orig_notes)
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def jaccard(orig_notes, gen_notes):
    def roll(ns):
        cells = set()
        for s, l, p in ns:
            for k in range(int(s * ROLL_PER_BEAT), max(int(s * ROLL_PER_BEAT) + 1, int((s + l) * ROLL_PER_BEAT))):
                cells.add((k, p))
        return cells
    a, b = roll(orig_notes), roll(gen_notes)
    return len(a & b) / len(a | b) if a | b else float("nan")


def style(bars, drums):
    notes = flat(bars)
    n_bars = len(bars)
    out = dict(notes_per_bar=len(notes) / n_bars if n_bars else 0,
               empty_bars=sum(1 for _, ns in bars if not ns))
    if not notes:
        return {**out, **{k: float("nan") for k in
                          ["max_poly", "mean_poly", "pitch_min", "pitch_max", "pitch_span", "note_len", "ioi"]}}
    onsets = Counter(round(s, 3) for s, _, _ in notes)
    starts = sorted(onsets)
    out.update(max_poly=max(onsets.values()), mean_poly=float(np.mean(list(onsets.values()))),
               note_len=float(np.mean([l for _, l, _ in notes])),
               ioi=float(np.mean(np.diff(starts))) if len(starts) > 1 else float("nan"))
    if drums:
        out.update(pitch_min=float("nan"), pitch_max=float("nan"), pitch_span=float("nan"))
    else:
        ps = [p for _, _, p in notes]
        out.update(pitch_min=min(ps), pitch_max=max(ps), pitch_span=max(ps) - min(ps))
    return out


# ---------- 곡 하나 평가 ----------
def evaluate(answer_path, gen_path, inst):
    orig, gen = load_bars(answer_path), load_bars(gen_path)
    n = min(len(orig), len(gen))
    orig, gen = orig[:n], gen[:n]
    drums = inst == "drums"
    on, gn = flat(orig), flat(gen)
    r = dict(bars=n)
    if drums:
        r.update(cp=float("nan"), cp_active=float("nan"), pche_orig=float("nan"),
                 pche_gen=float("nan"), pche_diff=float("nan"), pch_sim=float("nan"))
    else:
        cp, cpa = content_preservation(orig, gen)
        po, pg = entropy(pc_hist(on)), entropy(pc_hist(gn))
        r.update(cp=cp, cp_active=cpa, pche_orig=po, pche_gen=pg,
                 pche_diff=abs(po - pg) if not (math.isnan(po) or math.isnan(pg)) else float("nan"),
                 pch_sim=cos(pc_hist(on), pc_hist(gn)))
    go, gg = groove_consistency(orig), groove_consistency(gen)
    r.update(gs_orig=go, gs_gen=gg, gs_diff=abs(go - gg), gs_match=groove_match(orig, gen),
             f1=f1(on, gn), jaccard=jaccard(on, gn))
    for tag, b in (("orig", orig), ("gen", gen)):
        for k, v in style(b, drums).items():
            r[f"{k}_{tag}"] = v
    return r


def main():
    roots = sys.argv[1:] or ["step5_out"]
    rows = []
    for root in roots:
        model = os.path.basename(os.path.normpath(root))
        songs = sorted(s for s in os.listdir(root) if os.path.isdir(os.path.join(root, s)))
        for song in songs:
            for inst in INSTRUMENTS:
                d = os.path.join(root, song, inst)
                a, g = os.path.join(d, "answer_only.mid"), os.path.join(d, "generated_only.mid")
                if not (os.path.exists(a) and os.path.exists(g)):
                    continue
                try:
                    r = evaluate(a, g, inst)
                    rows.append(dict(model=model, song=song, instrument=inst, **r))
                except Exception as e:
                    print(f"  ⚠ {model}/{song}/{inst}: {type(e).__name__}: {e}")
        print(f"[{model}] 평가 {sum(1 for r in rows if r['model'] == model)}건")
    if not rows:
        print("평가할 파일(answer_only.mid + generated_only.mid)을 못 찾았어요. 폴더 경로를 확인해 주세요.")
        return

    fields = list(rows[0].keys())
    with open("eval_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in rows)

    show = ["cp", "cp_active", "gs_diff", "gs_match", "pche_diff", "pch_sim", "f1", "jaccard"]
    side = ["notes_per_bar", "empty_bars", "max_poly", "pitch_span", "note_len", "ioi"]
    summary = []
    for model in dict.fromkeys(r["model"] for r in rows):
        for inst in INSTRUMENTS:
            rs = [r for r in rows if r["model"] == model and r["instrument"] == inst]
            if not rs:
                continue
            m = lambda k: float(np.nanmean([r[k] for r in rs])) if any(not math.isnan(r[k]) for r in rs) else float("nan")
            s = dict(model=model, instrument=inst, n=len(rs), **{k: m(k) for k in show})
            for k in side:
                s[f"{k}_orig"], s[f"{k}_gen"] = m(f"{k}_orig"), m(f"{k}_gen")
            summary.append(s)
    with open("eval_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows({k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()} for s in summary)

    def fmt(v):
        return "  -  " if isinstance(v, float) and math.isnan(v) else f"{v:.3f}"
    print("\n=== 생성 품질 (원래 파트 대비) — ↑ 높을수록 좋음, ↓ 낮을수록 좋음 ===")
    print(f"{'모델':<12}{'악기':<8}{'곡':>3}  {'CP↑':>6}{'CP활성↑':>8}{'GS차이↓':>8}{'GS일치↑':>8}"
          f"{'PCHE차이↓':>10}{'PCH유사↑':>9}{'F1':>7}{'Jaccard':>8}")
    for s in summary:
        print(f"{s['model']:<12}{s['instrument']:<8}{s['n']:>3}  " + "".join(
            f"{fmt(s[k]):>{wd}}" for k, wd in zip(show, [6, 8, 8, 8, 10, 9, 7, 8])))
    print("\n=== 연주 가능성·스타일 (원래 → 생성) ===")
    print(f"{'모델':<12}{'악기':<8}{'마디당 음':>12}{'빈 마디':>12}{'최대 동시타건':>14}{'음역(반음)':>14}"
          f"{'평균 음길이(박)':>16}{'음 간격(박)':>13}")
    for s in summary:
        cells = [f"{fmt(s[k + '_orig'])}→{fmt(s[k + '_gen'])}" for k in side]
        print(f"{s['model']:<12}{s['instrument']:<8}" + "".join(
            f"{c:>{wd}}" for c, wd in zip(cells, [12, 12, 14, 14, 16, 13])))
    print("\n곡별 상세 → eval_results.csv  |  악기별 평균 → eval_summary.csv")


if __name__ == "__main__":
    main()
