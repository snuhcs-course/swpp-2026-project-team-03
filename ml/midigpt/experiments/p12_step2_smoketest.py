"""
[P12] MIDI-GPT 설치 확인 + 첫 생성 테스트 (Step 2)

하는 일
  1) 테스트용 8마디 MIDI(베이스·기타·드럼, 키보드 없음)를 만들거나, 인자로 준 MIDI를 읽음
  2) 빈 피아노(키보드) 트랙을 추가
  3) MIDI-GPT로 피아노 트랙을 생성 — 두 가지 설정으로 비교
       A. 제약 없음 (논문 기본 설정: temperature 1.0)
       B. 조성 제한(pitch_mask) + 동시음 최대 4개 제한 (연주 가능성용)
  4) 결과 MIDI 저장 + 처리 시간, 음 개수, 조성 안 음 비율, 최대 동시음 수 출력

사용법
  python p12_step2_smoketest.py                      # 장난감 곡으로 테스트
  python p12_step2_smoketest.py my_song.mid 0 major  # 내 MIDI, 조성 root=0(C), major

준비
  python3 -m venv .venv && source .venv/bin/activate     (Python 3.10~3.12)
  pip install "midigpt[inference]" pretty_midi
  첫 실행 때 HuggingFace에서 가중치를 자동 다운로드 (~/.cache/huggingface)
"""
import copy
import os
import sys
import time

import midigpt
import pretty_midi as pm
import torch
from midigpt.inference import GenerationRequest, InferenceConfig, InferenceEngine, TrackPrompt

MODEL = os.environ.get("ROCKY_MODEL", "yellow_medium")   # 예: ROCKY_MODEL=yellow_small
MASK_MODE = os.environ.get("ROCKY_MASK_MODE", "attention")  # yellow 모델은 "token" 미지원 → attention / remove
MODEL_DIM = int(os.environ.get("ROCKY_MODEL_DIM", "8"))     # 한 번에 보는 마디 수 (README 예시값 8)
PIANO_PROGRAM = 0          # General MIDI 0 = Acoustic Grand Piano
SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "natural_minor": (0, 2, 3, 5, 7, 8, 10)}


def pick_device():
    if os.environ.get("ROCKY_DEVICE"):  # 예: ROCKY_DEVICE=cpu (MPS 오류 시)
        return os.environ["ROCKY_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def make_toy_song(path="toy_no_keyboard.mid"):
    """C-G-Am-F 진행 8마디, 120BPM, 4/4. 베이스·기타(파워코드)·드럼만 있음."""
    m = pm.PrettyMIDI(initial_tempo=120)
    bass = pm.Instrument(program=33, name="Bass")
    gtr = pm.Instrument(program=29, name="Guitar")
    drums = pm.Instrument(program=0, is_drum=True, name="Drums")
    for bar, root in enumerate([48, 43, 45, 41] * 2):
        t0 = bar * 2.0  # 120BPM → 한 마디 2초
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


def add_empty_piano_track(score):
    """빈 트랙은 MIDI 로딩 시 사라지므로, dict로 풀어서 빈 피아노 트랙을 직접 추가."""
    d = score.to_dict()
    template = next(t for t in d["tracks"] if t["track_type"] != "drum")
    piano = copy.deepcopy(template)
    piano["instrument"] = PIANO_PROGRAM
    for bar in piano["bars"]:
        bar["notes"] = []
    d["tracks"].append(piano)
    return midigpt.Score.from_dict(d), len(d["tracks"]) - 1, len(piano["bars"])


def piano_stats(midi_path, key_root, scale):
    m = pm.PrettyMIDI(midi_path)
    pianos = [i for i in m.instruments if not i.is_drum and i.program == PIANO_PROGRAM]
    if not pianos:
        return "피아노 트랙 없음"
    notes = pianos[-1].notes
    if not notes:
        return "생성된 음 0개"
    allowed = {(key_root + iv) % 12 for iv in SCALES[scale]}
    in_key = sum(n.pitch % 12 in allowed for n in notes) / len(notes)
    events = sorted([(n.start, 1) for n in notes] + [(n.end, -1) for n in notes])
    cur = mx = 0
    for _, d in events:
        cur += d
        mx = max(mx, cur)
    lo, hi = min(n.pitch for n in notes), max(n.pitch for n in notes)
    return (f"음 {len(notes)}개 | 조성 안 음 비율 {in_key:.0%} | 최대 동시음 {mx} | "
            f"음역 {pm.note_number_to_name(lo)}~{pm.note_number_to_name(hi)}")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else make_toy_song()
    key_root = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    scale = sys.argv[3] if len(sys.argv) > 3 else "major"

    device = pick_device()
    print(f"[환경] midigpt {getattr(midigpt, '__version__', '?')} | torch {torch.__version__} | device={device}")

    t = time.time()
    engine = InferenceEngine.from_pretrained(MODEL, device=device)
    print(f"[로딩] {MODEL} {time.time() - t:.1f}s | mask_mode={MASK_MODE} | model_dim={MODEL_DIM}")

    score, piano_id, n_bars = add_empty_piano_track(midigpt.Score.from_midi(src))
    print(f"[입력] {src} | 트랙 {piano_id + 1}개(피아노 포함) | {n_bars}마디")

    settings = {
        "A_free": dict(controls={}, cfg=dict()),
        "B_key_poly4": dict(controls={"pitch_mask": {"scale": scale, "root": key_root}},
                            cfg=dict(polyphony_hard_limit=4)),
    }
    for name, s in settings.items():
        req = GenerationRequest(
            tracks=[TrackPrompt(id=i, bars=[]) for i in range(piano_id)] + [TrackPrompt(id=piano_id, bars=list(range(n_bars)), controls=s["controls"])],
            config=InferenceConfig(temperature=1.0, seed=42, mask_mode=MASK_MODE,
                                   model_dim=min(MODEL_DIM, n_bars), **s["cfg"]),
        )
        t = time.time()
        result = engine.session(score, req).run()
        dt = time.time() - t
        out = f"out_{name}.mid"
        result.to_midi(out)
        print(f"[{name}] {dt:.1f}s ({dt / n_bars:.2f}s/마디) → {out}")
        print(f"        {piano_stats(out, key_root, scale)}")

    print("\n→ 결과 MIDI를 GarageBand/MuseScore로 열어 들어보고, 위 숫자와 함께 팀 공유 폴더에 올려주세요.")


if __name__ == "__main__":
    main()
