"""
[P12] MIDI-GPT 악기 파트 생성 (Iteration 1 의 p12_step5_generate4.py)
  - 한 곡 단위로는 generate_missing.py 를 쓰세요. 이 파일은 폴더 안 여러 곡을 한꺼번에 처리합니다.

실험 규칙 (예: 피아노 실험)
  - 피아노로 분류된 트랙은 '전부' 지움 (피아노가 2개면 2개 다)
  - 피아노가 아닌 트랙은 4대 악기 외(스트링·신스 등)까지 '전부' 남김
  - 곡 '전체 길이'를 입력으로 넣고, 피아노 트랙 1개를 처음부터 끝까지 생성
  - 원곡에 그 악기가 아예 없으면: 지울 게 없으니 그대로 넣고 새로 생성 (정답 없음으로 기록)

폴더 구조는 두 가지 모두 지원
  A) TrackXXXXX/MIDI/piano.mid, guitar.mid, bass.mid, drums.mid (+ 다른 .mid)
  B) TrackXXXXX/MIDI/S00.mid, S01.mid ... + metadata.yaml   (Slakh 원본 형식)

출력: step5_out/TrackXXXXX/
  _source/            원곡 원본 파일 그대로 복사 (MIDI 폴더, all_src.mid, metadata.yaml)
  song_original.mid   원곡 전체를 한 파일로 합친 것 (모든 트랙, 지운 것 없음)
step5_out/TrackXXXXX/<악기>/
  input.mid           모델 입력 (그 악기를 전부 뺀 곡)
  original.mid        원곡 전체                         ← 음원 평가용
  generated.mid       입력 + 생성된 그 악기             ← 음원 평가용
  answer_only.mid     원래 그 악기 파트만 (없으면 생략)   ← 지표 계산용
  generated_only.mid  생성된 그 악기 파트만             ← 지표 계산·악보용
step5_log.csv : 곡·악기별 결과 (마디 수, 트랙 수, 음 개수, 시간, 오류)

사용법
  python generate_part.py data/babyslakh_16k                     # 20곡 × 4악기, 전체 길이
  ROCKY_SONGS=1 python generate_part.py data/babyslakh_16k       # 시험: 1곡만 (시간 측정용)
  ROCKY_INST=drums python ...    ROCKY_MODEL=yellow_small python ...   ROCKY_DEVICE=cpu python ...
  ROCKY_BARS=16 python ...       # 앞 16마디만 (0 = 전체, 기본값)
  중간에 멈춰도 같은 명령을 다시 실행하면 끝난 곡·악기는 건너뛰고 이어서 진행해요.
"""
import copy
import csv
import glob
import os
import shutil
import sys
import time

import midigpt
import torch
import yaml
from midigpt.inference import GenerationRequest, InferenceConfig, InferenceEngine, TrackPrompt

MODEL = os.environ.get("ROCKY_MODEL", "yellow_medium")
N_BARS = int(os.environ.get("ROCKY_BARS", "0"))               # 0 = 곡 전체
MAX_SONGS = int(os.environ.get("ROCKY_SONGS", "0"))           # 0 = 전부
TARGETS = [s.strip() for s in os.environ.get("ROCKY_INST", "piano,guitar,bass,drums").split(",") if s.strip()]
SEED = int(os.environ.get("ROCKY_SEED", "0"))
OUT = os.environ.get("ROCKY_OUT", "step5_out")
LOG = os.environ.get("ROCKY_LOG", "step5_log.csv")
SLAKH_CLASS = {"piano": "Piano", "guitar": "Guitar", "bass": "Bass", "drums": "Drums"}
# 원곡에 그 악기가 없을 때 쓸 악기 번호 (General MIDI)
DEFAULT_PROGRAM = {"piano": 0, "guitar": 27, "bass": 33, "drums": 0}
TEMPO = 500000   # 4분음표당 마이크로초 (MIDI 템포 단위). 곡마다 원본 값으로 바꿈


def pick_device():
    if os.environ.get("ROCKY_DEVICE"):
        return os.environ["ROCKY_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ---------- 곡 불러오기 ----------
def load_tracks(midi_path, label, res):
    s = midigpt.Score.from_midi(midi_path)
    if s.resolution != res:
        s = s.resample(res)
    return [(label, t) for t in s.to_dict()["tracks"]]


def song_files(song_dir):
    """[(악기라벨, MIDI 경로)] — 라벨: piano/guitar/bass/drums/other"""
    mdir = os.path.join(song_dir, "MIDI")
    named = {k: os.path.join(mdir, f"{k}.mid") for k in SLAKH_CLASS}
    if any(os.path.exists(p) for p in named.values()):                        # 형식 A
        files = [(k, p) for k, p in named.items() if os.path.exists(p)]
        return files + [("other", p) for p in sorted(glob.glob(os.path.join(mdir, "*.mid")))
                        if p not in named.values()]
    meta_path = os.path.join(song_dir, "metadata.yaml")                       # 형식 B
    meta = yaml.safe_load(open(meta_path)) if os.path.exists(meta_path) else {}
    stems = (meta or {}).get("stems", {}) or {}
    files = []
    for p in sorted(glob.glob(os.path.join(mdir, "*.mid"))):
        info = stems.get(os.path.splitext(os.path.basename(p))[0], {}) or {}
        label = "drums" if info.get("is_drum") else next(
            (k for k, v in SLAKH_CLASS.items() if v == info.get("inst_class")), "other")
        files.append((label, p))
    return files


def load_song(song_dir):
    files = song_files(song_dir)
    if not files:
        return None, None, []
    first = midigpt.Score.from_midi(files[0][1])
    res, tempo = first.resolution, int(first.tempo or 500000)
    tracks = []
    for label, p in files:
        try:
            tracks += [(lab, t) for lab, t in load_tracks(p, label, res)
                       if sum(len(b["notes"]) for b in t["bars"]) > 0]
        except Exception as e:
            print(f"      (읽기 실패, 건너뜀: {os.path.basename(p)} — {e})")
    return res, tempo, tracks


def n_notes(t):
    return sum(len(b["notes"]) for b in t["bars"])


def align(tracks):
    """모든 트랙을 같은 마디 수로 맞춤: 가장 긴 트랙 기준, 짧은 트랙은 빈 마디로 채움."""
    ref = max((t for _, t in tracks), key=lambda t: len(t["bars"]))
    n = len(ref["bars"]) if N_BARS == 0 else min(len(ref["bars"]), N_BARS)
    out = []
    for label, t in tracks:
        t = copy.deepcopy(t)
        bars = t["bars"][:n]
        for i in range(len(bars), n):
            empty = {k: v for k, v in ref["bars"][i].items() if k != "notes"}
            empty["notes"] = []
            bars.append(empty)
        t["bars"] = bars
        out.append((label, t))
    ts = sorted({(b.get("ts_numerator", 4), b.get("ts_denominator", 4)) for b in ref["bars"][:n]})
    return out, n, ts


def build(tracks, target, res):
    answer = [t for lab, t in tracks if lab == target]
    context = [t for lab, t in tracks if lab != target]          # 4대 악기 외 포함 전부 유지
    if not context:
        return None, "다른 악기 없음"
    if answer:
        empty = copy.deepcopy(answer[0])                         # 원래 악기 번호·종류 그대로
    else:
        empty = copy.deepcopy(context[0])
        empty["instrument"] = DEFAULT_PROGRAM[target]
        empty["track_type"] = "drum" if target == "drums" else "melodic"
    for b in empty["bars"]:
        b["notes"] = []
    score = midigpt.Score.from_dict({"resolution": res, "tempo": TEMPO, "tracks": context + [empty]})
    memo = f"입력 {len(context)}트랙 / 지운 {target} {len(answer)}트랙" + ("" if answer else " (원곡에 없음)")
    return (score, context, answer), memo


def save(path, res, tracks):
    midigpt.Score.from_dict({"resolution": res, "tempo": TEMPO, "tracks": tracks}).to_midi(path)


def save_source(song_dir, song_out, res, tracks):
    """원곡 보관: 원본 파일 그대로(_source/) + 모든 트랙을 합친 song_original.mid"""
    src = os.path.join(song_out, "_source")
    if not os.path.exists(src):
        os.makedirs(src, exist_ok=True)
        shutil.copytree(os.path.join(song_dir, "MIDI"), os.path.join(src, "MIDI"), dirs_exist_ok=True)
        for f in ("all_src.mid", "metadata.yaml"):
            if os.path.exists(os.path.join(song_dir, f)):
                shutil.copy2(os.path.join(song_dir, f), src)
    merged = os.path.join(song_out, "song_original.mid")
    if not os.path.exists(merged):
        save(merged, res, [t for _, t in tracks])


# 악기별 '한 번에 누르는 음' 상한 (연주 가능 범위 + 생성이 너무 길어지는 것 방지)
POLY_LIMIT = {"piano": 6, "guitar": 6, "bass": 2, "drums": 4}
# 시도 순서: (창 마디 수, 마디당 음 상한, 빈 마디·원본동일 검사, temperature)
ATTEMPTS = [
    (8, 32, True, 1.0),    # 기본: 8마디 창
    (4, 32, False, 1.0),   # 실패 시: 4마디 창, 일부 마디가 비어도 허용
    (4, 16, False, 0.9),   # 그래도 실패 시: 음 상한을 더 낮춰 짧게 생성
    (4, 0, False, 1.0),    # 마지막: 상한 모두 끔(0) — 상한 때문에 '쓸 수 있는 토큰 0개' 충돌이 날 때
]


def generate(engine, score, pid, n_bars, inst):
    """창 크기·음 상한을 바꿔가며 최대 3번 시도. 성공한 설정을 함께 반환."""
    last = None
    for dim, density, checks, temp in ATTEMPTS:
        dim = min(dim, n_bars)
        req = GenerationRequest(
            tracks=[TrackPrompt(id=j, bars=[]) for j in range(pid)]
            + [TrackPrompt(id=pid, bars=list(range(n_bars)), autoregressive=True)],
            config=InferenceConfig(temperature=temp, seed=SEED, mask_mode="attention", model_dim=dim,
                                   polyphony_hard_limit=POLY_LIMIT.get(inst, 6) if density else 0,
                                   density_hard_limit=density,
                                   silence_check=checks, novelty_check=checks, max_attempts=3),
        )
        try:
            gen = engine.session(score, req).run().to_dict()["tracks"][pid]
            if n_notes(gen) > 0:
                return gen, f"{dim}마디창/음상한{density}"
            last = RuntimeError("생성된 음 0개")
        except Exception as e:
            last = e
        print(f"        (창 {dim}마디·음상한 {density} 실패: {str(last)[:70]} → 다음 설정으로 재시도)")
    raise last


def empty_bars(t):
    return sum(1 for b in t["bars"] if not b["notes"])


def main():
    global TEMPO
    if len(sys.argv) < 2:
        print("사용법: python generate_part.py <babyslakh 폴더 경로>")
        return
    songs = sorted(d for d in glob.glob(os.path.join(sys.argv[1], "**", "Track*"), recursive=True)
                   if os.path.isdir(os.path.join(d, "MIDI")))
    if not songs:
        print(f"'{sys.argv[1]}' 아래에서 Track*/MIDI 폴더를 못 찾았어요. 경로를 확인해 주세요.")
        return
    if MAX_SONGS:
        songs = songs[:MAX_SONGS]
    device = pick_device()
    print(f"[환경] midigpt {getattr(midigpt, '__version__', '?')} | device={device} | 모델={MODEL} | "
          f"곡 {len(songs)}개 × 악기 {TARGETS} | {'전체 길이' if N_BARS == 0 else f'앞 {N_BARS}마디'}")
    engine = InferenceEngine.from_pretrained(MODEL, device=device)

    fields = ["song", "instrument", "status", "bars", "time_sig", "context_tracks", "removed_tracks",
              "answer_notes", "gen_notes", "gen_empty_bars", "window", "seconds", "sec_per_bar", "error"]
    new_log = not os.path.exists(LOG)
    logf = open(LOG, "a", newline="", encoding="utf-8-sig")
    log = csv.DictWriter(logf, fieldnames=fields)
    if new_log:
        log.writeheader()

    jobs_total = len(songs) * len(TARGETS)
    t_all, done, gen_time = time.time(), 0, 0.0
    for si, song_dir in enumerate(songs, 1):
        song = os.path.basename(song_dir.rstrip("/"))
        res, tempo, tracks = load_song(song_dir)
        if not tracks:
            print(f"[{si}/{len(songs)}] {song}: MIDI 없음, 건너뜀")
            continue
        TEMPO = tempo
        tracks, n_bars, ts = align(tracks)
        labels = {}
        for lab, _ in tracks:
            labels[lab] = labels.get(lab, 0) + 1
        print(f"[{si}/{len(songs)}] {song}: {n_bars}마디, 박자 {ts}, 트랙 {len(tracks)}개 {labels}")
        save_source(song_dir, os.path.join(OUT, song), res, tracks)

        for inst in TARGETS:
            outdir = os.path.join(OUT, song, inst)
            if os.path.exists(os.path.join(outdir, "generated_only.mid")):
                print(f"      {inst:<7}: 이미 완료, 건너뜀")
                continue
            built, memo = build(tracks, inst, res)
            if built is None:
                print(f"      {inst:<7}: 건너뜀 — {memo}")
                log.writerow(dict(song=song, instrument=inst, status="skip", bars=n_bars, error=memo))
                continue
            score, context, answer = built
            row = dict(song=song, instrument=inst, bars=n_bars, time_sig=str(ts),
                       context_tracks=len(context), removed_tracks=len(answer),
                       answer_notes=sum(n_notes(t) for t in answer))
            t0 = time.time()
            try:
                gen, dim = generate(engine, score, len(context), n_bars, inst)
                dt = time.time() - t0
                os.makedirs(outdir, exist_ok=True)
                save(os.path.join(outdir, "input.mid"), res, context)
                save(os.path.join(outdir, "original.mid"), res, context + answer)
                save(os.path.join(outdir, "generated.mid"), res, context + [gen])
                if answer:
                    save(os.path.join(outdir, "answer_only.mid"), res, answer)
                save(os.path.join(outdir, "generated_only.mid"), res, [gen])
                row.update(status="ok" if answer else "ok_no_original", gen_notes=n_notes(gen),
                           gen_empty_bars=empty_bars(gen),
                           window=dim, seconds=round(dt, 1), sec_per_bar=round(dt / n_bars, 2))
                done += 1
                gen_time += dt
                left = jobs_total - (si - 1) * len(TARGETS) - (TARGETS.index(inst) + 1)
                eta = gen_time / done * max(left, 0) / 60
                print(f"      {inst:<7}: {dt:.0f}s ({dt / n_bars:.2f}s/마디) | {memo} | "
                      f"음 개수 원래 {row['answer_notes']} / 생성 {row['gen_notes']} | 빈 마디 {row['gen_empty_bars']} | "
                      f"{dim} | 남은 시간 약 {eta:.0f}분")
            except Exception as e:
                dt = time.time() - t0
                row.update(status="error", seconds=round(dt, 1), error=f"{type(e).__name__}: {e}"[:200])
                print(f"      {inst:<7}: ⚠ 실패 — {row['error']}")
            log.writerow(row)
            logf.flush()

    logf.close()
    print(f"\n완료: 이번 실행에서 생성 {done}건 | 총 {(time.time() - t_all) / 60:.1f}분")
    print(f"결과 → {OUT}/<곡>/<악기>/  |  처리 기록 → {LOG}")


if __name__ == "__main__":
    main()
