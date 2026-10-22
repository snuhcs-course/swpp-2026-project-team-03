"""
[P12] Step 3 — 논문 7.3절 "Attribute Control" 실험 소규모 재현

논문 실험 (MIDI-GPT, AAAI 2025, 7.3절)
  - 8마디 구간을 속성 조건(음 밀도, 동시음 수, 음 길이)을 걸고 100번 생성
  - 요청한 단계와 실제로 나온 단계를 비교
  - 논문 결과: 음 밀도는 차이가 대부분 0, 1을 넘는 경우 드묾 → 잘 먹힘
               음 길이는 대체로 먹힘 / 동시음 수는 약함

이 스크립트 (축소판)
  - 입력 곡(기본: 2단계 연습곡)의 첫 8마디에 빈 피아노 트랙을 붙이고
  - 모델이 지원하는 속성마다 낮음/중간/높음 3단계를 요청해 N번씩 생성
  - 결과에서 실제 단계를 측정(패키지 내장 분석기 사용) → 요청과 비교
  - 결과: 화면 요약표 + step3_results.csv (시도별 기록)

사용법
  python p12_step3_paper_repro.py                    # 연습곡, 단계당 3회
  ROCKY_TRIALS=5 python p12_step3_paper_repro.py     # 단계당 5회
  python p12_step3_paper_repro.py 곡.mid             # 다른 MIDI (첫 8마디만 사용)
  ROCKY_MODEL=yellow_small python p12_step3_paper_repro.py   # 논문 크기에 가까운 모델
"""
import copy
import csv
import os
import statistics
import sys
import time

import midigpt
import pretty_midi as pm
import torch
from midigpt.inference import GenerationRequest, InferenceConfig, InferenceEngine, TrackPrompt

MODEL = os.environ.get("ROCKY_MODEL", "yellow_small")
TRIALS = int(os.environ.get("ROCKY_TRIALS", "3"))
N_BARS = 8                      # 논문과 같은 8마디 구간
PIANO_PROGRAM = 0
# 논문 7.3절에 나온 속성 (패키지 이름 기준). 모델이 지원하는 것만 자동으로 사용.
PAPER_ATTRS = ["note_density", "min_polyphony", "max_polyphony",
               "min_note_duration", "max_note_duration"]


def pick_device():
    if os.environ.get("ROCKY_DEVICE"):
        return os.environ["ROCKY_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def make_toy_song(path="toy_no_keyboard.mid"):
    """2단계와 같은 연습곡: C-G-Am-F 8마디, 베이스·기타·드럼."""
    if os.path.exists(path):
        return path
    m = pm.PrettyMIDI(initial_tempo=120)
    bass = pm.Instrument(program=33, name="Bass")
    gtr = pm.Instrument(program=29, name="Guitar")
    drums = pm.Instrument(program=0, is_drum=True, name="Drums")
    for bar, root in enumerate([48, 43, 45, 41] * 2):
        t0 = bar * 2.0
        for k in range(4):
            bass.notes.append(pm.Note(90, root - 12, t0 + k * 0.5, t0 + k * 0.5 + 0.45))
        for k in range(8):
            for iv in (0, 7, 12):
                gtr.notes.append(pm.Note(80, root + iv, t0 + k * 0.25, t0 + k * 0.25 + 0.2))
        for k in range(4):
            drums.notes.append(pm.Note(100, 36 if k % 2 == 0 else 38, t0 + k * 0.5, t0 + k * 0.5 + 0.1))
    m.instruments = [bass, gtr, drums]
    m.write(path)
    return path


def prepare_score(path):
    """첫 8마디만 남기고, 기존 피아노(0~7번 악기)는 빼고, 빈 피아노 트랙 추가."""
    d = midigpt.Score.from_midi(path).to_dict()
    tracks = [t for t in d["tracks"] if t["track_type"] == "drum" or t["instrument"] > 7]
    if len(tracks) < len(d["tracks"]):
        print(f"[입력] 원래 있던 피아노 계열 트랙 {len(d['tracks']) - len(tracks)}개는 제외했어요")
    for t in tracks:
        t["bars"] = t["bars"][:N_BARS]
    template = next(t for t in tracks if t["track_type"] != "drum")
    piano = copy.deepcopy(template)
    piano["instrument"] = PIANO_PROGRAM
    for bar in piano["bars"]:
        bar["notes"] = []
    tracks.append(piano)
    d["tracks"] = tracks
    return midigpt.Score.from_dict(d), len(tracks) - 1, len(piano["bars"])


def pick_levels(size):
    """낮음/중간/높음 3단계 (예: 10단계 → 1, 4, 8)."""
    return sorted({max(0, round(size * 0.15)), size // 2 - 1 if size > 3 else 1, size - 2})


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else make_toy_song()
    device = pick_device()
    print(f"[환경] midigpt {getattr(midigpt, '__version__', '?')} | device={device} | 모델={MODEL} | 단계당 {TRIALS}회")

    engine = InferenceEngine.from_pretrained(MODEL, device=device)
    analyzer = engine._analyzer
    sizes = analyzer.attribute_sizes()
    levels_of = analyzer.attribute_levels()
    types_of = analyzer.attribute_track_types()
    print(f"[모델이 지원하는 속성] {sizes}")

    attrs = [a for a in PAPER_ATTRS
             if a in sizes and levels_of.get(a) == "track" and types_of.get(a) in ("melodic", "both")]
    skipped = [a for a in PAPER_ATTRS if a not in attrs]
    print(f"[이번 실험 속성] {attrs}" + (f"  (지원 안 함/피아노 적용 불가: {skipped})" if skipped else ""))
    if not attrs:
        print("피아노 트랙에 걸 수 있는 속성이 없어요. 위 [모델이 지원하는 속성] 줄을 채팅에 붙여주세요.")
        return

    score, piano_id, n_bars = prepare_score(src)
    print(f"[입력] {src} | 트랙 {piano_id + 1}개(피아노 포함) | {n_bars}마디")

    plan = [(a, lv) for a in attrs for lv in pick_levels(sizes[a])]
    total = len(plan) * TRIALS
    print(f"[계획] {len(plan)}개 조건 × {TRIALS}회 = {total}번 생성\n")

    rows, done, t_all = [], 0, time.time()
    for attr, level in plan:
        for trial in range(TRIALS):
            req = GenerationRequest(
                tracks=[TrackPrompt(id=i, bars=[]) for i in range(piano_id)]
                + [TrackPrompt(id=piano_id, bars=list(range(n_bars)), autoregressive=True,
                               attributes={attr: level})],
                config=InferenceConfig(temperature=1.0, seed=trial, mask_mode="attention",
                                       model_dim=min(8, n_bars)),
            )
            t = time.time()
            try:
                result = engine.session(score, req).run()
                n_notes = sum(len(b["notes"]) for b in result.to_dict()["tracks"][piano_id]["bars"])
                if n_notes == 0:
                    raise RuntimeError("피아노에 생성된 음이 0개 (생성이 실행되지 않음)")
                realized = analyzer.report(result, piano_id, {attr: level})["track"][attr]["realized"]
                err = ""
            except Exception as e:  # 한 번 실패해도 나머지는 계속
                realized, err = None, f"{type(e).__name__}: {e}"[:200]
            dt = time.time() - t
            done += 1
            diff = None if realized is None else abs(realized - level)
            rows.append(dict(attribute=attr, requested=level, realized=realized,
                             abs_diff=diff, seconds=round(dt, 1), error=err))
            eta = (time.time() - t_all) / done * (total - done)
            print(f"  [{done}/{total}] {attr}={level} → 실제 {realized} "
                  f"({dt:.1f}s, 남은 시간 약 {eta / 60:.1f}분){'  ⚠ ' + err if err else ''}")

    with open("step3_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n=== 요약 (논문 7.3절 방식: 요청 단계와 실제 단계의 차이) ===")
    print(f"{'속성':<20}{'시도':>5}{'정확히 일치':>12}{'차이≤1':>10}{'평균 차이':>10}")
    for attr in attrs:
        ok = [r for r in rows if r["attribute"] == attr and r["abs_diff"] is not None]
        if not ok:
            print(f"{attr:<20}{'실패':>5}")
            continue
        d = [r["abs_diff"] for r in ok]
        exact = sum(x == 0 for x in d) / len(d)
        within1 = sum(x <= 1 for x in d) / len(d)
        print(f"{attr:<20}{len(d):>5}{exact:>12.0%}{within1:>10.0%}{statistics.mean(d):>10.2f}")
    fails = sum(1 for r in rows if r["error"])
    print(f"\n생성 실패 {fails}건 | 총 {(time.time() - t_all) / 60:.1f}분 | 시도별 기록 → step3_results.csv")
    print("논문 기준: note_density는 차이 대부분 0·1 이하(잘 먹힘), 동시음(polyphony)은 약함")


if __name__ == "__main__":
    main()
