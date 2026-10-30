"""ROCKY beat alignment.

MuScriptor가 기본 120 BPM 그리드로 써 준 MIDI를 Beat This!가 찾은
실제 박/다운비트 위에 다시 올려, 템포 하나 + 박자 하나의 마디로 정리한다.
박자(마디당 박 수)는 다운비트 사이의 박 수 중 가장 많이 나온 값으로 정한다.

    python align.py --midi song.mid --audio song.wav --out song_aligned.mid
    python align.py --midi-dir midi/ --audio-dir audio/ --out-dir aligned/
    python align.py --midi song.mid --beats song_beats.json --out song_aligned.mid --bpm 108 --triplets

--bpm: 곡의 실제 템포를 알 때, Beat This!가 1.5배·2배·절반 간격으로 찍은 구간의 박을 그 템포로 다시 센다.
--triplets: 박마다 16분음표 칸과 셋잇단 8분음표 칸 중 음들에 더 잘 맞는 쪽으로 맞춘다 (4/4 곡 안의 셋잇단).
--compound: 겹박자(6/8, 12/8). 한 박 = 점4분음표로 보고 8분음표 3개(16분음표 6개)로 나눠 맞추고, n/8 박자표를 쓴다.

자동 판별 (기본으로 켜짐, --no-auto-meter로 끔):
  - 12/8 감지: Beat This! 박 간격에 "한 박"과 "그 2/3"이 둘 다 많고, 박 안의 음이 셋잇단 자리에 많으면
    겹박자로 보고 박을 점4분음표 단위로 다시 센다 (detect_compound → fix_beats).
  - 마디선: 드럼 MIDI의 스네어가 2·4박, 킥이 1박에 오도록 마디 첫 박을 고른다 (drum_bar_phase).
  --compound, --downbeat-shift를 직접 주면 그 값을 쓴다.

beat_this.ipynb (Colab)의 correct_midi() 로직을 그대로 옮긴 것이다.

Alignment logic from beat_this.ipynb (Soobin Jo); refactored into a module with Claude (AI).
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pretty_midi

# BPM 계산에서 제외할 비정상 박 간격 (초). 0.2 s = 300 BPM, 2.0 s = 30 BPM
MIN_BEAT_INTERVAL = 0.2
MAX_BEAT_INTERVAL = 2.0
DEFAULT_BEATS_PER_BAR = 4   # 다운비트가 없거나 부족할 때 쓰는 박자 (4/4)
MIN_BEATS_PER_BAR = 2       # 이 범위 밖의 다운비트 간격은 박자 추정에서 제외
MAX_BEATS_PER_BAR = 12
SUBDIVISION = 4          # 1박 = 16분음표 4개
TRIPLET_SUBDIVISION = 3  # 1박 = 셋잇단 8분음표 3개 (--triplets)
TRIPLET_MARGIN = 0.6     # 셋잇단 칸 오차가 16분음표 칸 오차의 60% 미만일 때만 셋잇단으로 본다
TRIPLET_MIN_OFFBEAT = 2  # 한 박 안에 박 위가 아닌 음이 2개 이상 있어야 판단한다
BPM_FIX_TOLERANCE = 0.15 # --bpm: 박 간격이 기대 간격(x1, x2/3, x1/2, x2)의 ±15% 안이면 그 배수로 본다
COMPOUND_SUBDIVISION = 6 # --compound: 점4분음표 한 박 = 16분음표 6개
RESOLUTION = 480         # 3과 4로 모두 나누어떨어져야 셋잇단 위치가 정확하다
TEMPO_MEAN_WINDOW = 0.08 # 템포: 중앙값 ±8% 안의 박 간격 평균 (박 시각이 0.02 s 단위라 중앙값만 쓰면 1~2% 틀어짐)
COMPOUND_MIN_LEVEL = 0.10    # 자동 12/8: 두 박 단위(x1, x2/3) 중 적은 쪽이 박 간격의 10% 이상이고
COMPOUND_MIN_TRIPLET = 0.12  #           박 위가 아닌 음 중 셋잇단 자리에 확실히 가까운 음이 12% 이상
PHASE_MIN_GAIN = 0.25        # 자동 마디선: 드럼 점수가 이만큼 좋아질 때만 Beat This! 마디선을 옮긴다
KICK_PITCHES = (35, 36)
SNARE_PITCHES = (37, 38, 40)


@dataclass
class AlignResult:
    bpm: float
    note_count: int
    beat_offset: int
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    triplet_beats: int = 0
    compound: bool = False
    downbeat_shift: int = 0

    @property
    def meter(self) -> str:
        return f"{self.beats_per_bar * 3}/8" if self.compound else f"{self.beats_per_bar}/4"


# ----------------------------------------------------------------------
# 1. Beat This! 추론
# ----------------------------------------------------------------------
_FILE2BEATS_CACHE: dict = {}


def _get_file2beats(device: str, checkpoint: str):
    """Beat This! 모델을 (device, checkpoint)별로 한 번만 불러온다."""
    import torch  # 무거운 의존성은 필요할 때만 import
    from beat_this.inference import File2Beats

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    key = (device, checkpoint)
    if key not in _FILE2BEATS_CACHE:
        _FILE2BEATS_CACHE[key] = File2Beats(checkpoint_path=checkpoint, device=device, dbn=False)
    return _FILE2BEATS_CACHE[key]


def detect_beats(audio_path: str | Path, device: str = "auto",
                 checkpoint: str = "final0") -> tuple[list[float], list[float]]:
    """오디오에서 박과 다운비트 시각(초)을 찾는다.

    ROCKY 설계상 입력은 보컬 제거 전 **원곡 오디오**다.
    """
    beats, downbeats = _get_file2beats(device, checkpoint)(str(audio_path))
    return np.asarray(beats).tolist(), np.asarray(downbeats).tolist()


def save_beats(path: str | Path, beats: Sequence[float], downbeats: Sequence[float]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"beats": list(beats), "downbeats": list(downbeats)}, f, indent=2)


def load_beats(path: str | Path) -> tuple[list[float], list[float]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["beats"], data["downbeats"]


# ----------------------------------------------------------------------
# 2. MIDI 보정
# ----------------------------------------------------------------------
def estimate_bpm(beats: np.ndarray) -> tuple[float, float]:
    """박 간격으로 BPM을 구한다. (bpm, 대표 간격 초)

    중앙값 ±8% 안에 드는 간격들의 평균을 쓴다. Beat This!는 박을 0.02 s 단위로 찍어서
    중앙값은 0.46 s, 0.48 s처럼 계단식으로만 나오고 BPM이 1~2% 틀어진다 (10곡 평균 오차 1.07% → 0.43%).
    """
    intervals = np.diff(beats)
    valid = intervals[(intervals > MIN_BEAT_INTERVAL) & (intervals < MAX_BEAT_INTERVAL)]
    if len(valid) == 0:
        raise ValueError("유효한 박 간격이 없습니다.")
    median = float(np.median(valid))
    interval = float(np.mean(valid[np.abs(valid / median - 1) <= TEMPO_MEAN_WINDOW]))
    return 60.0 / interval, interval


def _downbeat_indices(beats: np.ndarray, downbeats: np.ndarray) -> list[int]:
    """각 다운비트에 가장 가까운 박의 번호 (중복 제거, 오름차순)."""
    return sorted({int(np.argmin(np.abs(beats - d))) for d in downbeats})


def estimate_beats_per_bar(beats: np.ndarray, downbeats: np.ndarray) -> int:
    """다운비트 사이 박 수 중 가장 많이 나온 값을 곡 전체의 박자로 쓴다.

    Beat This!가 마디 중간에 다운비트를 하나 더 찍거나(2+2) 하나 놓치는(8) 일이 있어도
    대부분의 마디가 맞으면 결과가 흔들리지 않는다. 진짜로 박자가 바뀌는 곡은 따라가지 못한다.
    다운비트가 2개 미만이거나 쓸 만한 간격이 없으면 4를 돌려준다.
    """
    beats = np.asarray(beats, dtype=float)
    downbeats = np.asarray(downbeats, dtype=float)
    if len(beats) == 0 or len(downbeats) < 2:
        return DEFAULT_BEATS_PER_BAR
    gaps = np.diff(_downbeat_indices(beats, downbeats))
    gaps = [int(g) for g in gaps if MIN_BEATS_PER_BAR <= g <= MAX_BEATS_PER_BAR]
    if not gaps:
        return DEFAULT_BEATS_PER_BAR
    counts = Counter(gaps)
    top = max(counts.values())
    tied = [g for g, c in counts.items() if c == top]
    # 동률이면 4/4를 우선하고, 아니면 작은 값
    return DEFAULT_BEATS_PER_BAR if DEFAULT_BEATS_PER_BAR in tied else min(tied)


def compute_beat_offset(beats: np.ndarray, downbeats: np.ndarray,
                        beats_per_bar: int = DEFAULT_BEATS_PER_BAR) -> int:
    """첫 다운비트가 마디 첫 박(beats_per_bar의 배수)에 오도록 하는 박 오프셋."""
    if len(downbeats) == 0:
        return 0
    nearest_idx = int(np.argmin(np.abs(beats - downbeats[0])))
    return (-nearest_idx) % beats_per_bar


BPM_FIX_RATIOS = (1.0, 2 / 3, 0.5, 2.0)   # 찍힌 박 간격 = 실제 박 x 이 값
BPM_FIX_MIN_RUN = 3                      # 같은 배수가 이만큼 이어진 구간만 믿는다


def fix_beats(beats: Sequence[float], downbeats: Sequence[float],
              bpm: float) -> tuple[np.ndarray, np.ndarray]:
    """곡의 실제 템포(bpm)를 알 때 박을 그 템포로 다시 센다.

    Beat This!는 셋잇단이 많은 구간에서 박을 1.5배 빠르게(실제 박의 2/3 간격) 찍거나,
    두 배·절반으로 찍기도 한다. 그러면 곡 전체 템포(박 간격의 중앙값)도 틀어진다.

    1. 박 간격마다 실제 박의 1, 2/3, 1/2, 2배 중 어디에 해당하는지 정한다 (±15%).
    2. 같은 배수가 BPM_FIX_MIN_RUN개 이상 이어진 구간만 쓰고, 구간 안에서는 실제 박 번호를 센다.
       구간 사이(애매한 간격)에서는 세지 않는다. 대신 지금까지 센 정박들로 맞춘
       "시각 = t0 + 번호 x 한 박 길이" 직선으로 다음 구간의 시작 번호를 정한다.
       그래서 애매한 간격이 쌓여도 박 위치(위상)가 밀리지 않는다.
    3. 정수 번호마다 찍힌 박 시각을 보간해 새 박을 만든다.
    다운비트는 원래 박자와 첫 다운비트 위치로 다시 만든다.
    """
    b = np.unique(np.asarray(beats, dtype=float))
    if len(b) < 2:
        raise ValueError("박이 2개 미만입니다.")
    iv = np.diff(b)
    period = 60.0 / bpm
    ratio = np.full(len(iv), np.nan)
    for r in BPM_FIX_RATIOS:
        hit = np.isnan(ratio) & (np.abs(iv / (period * r) - 1) < BPM_FIX_TOLERANCE)
        ratio[hit] = r
    runs, s = [], 0
    for k in range(1, len(iv) + 1):
        if k == len(iv) or not (ratio[k] == ratio[s] or (np.isnan(ratio[k]) and np.isnan(ratio[s]))):
            runs.append((s, k, ratio[s]))
            s = k
    count = np.full(len(b), np.nan)
    t0 = None
    known_k: list[float] = []
    known_t: list[float] = []
    for s, e, r in runs:
        if np.isnan(r) or e - s < BPM_FIX_MIN_RUN:
            continue
        if t0 is None:
            c0, t0 = 0.0, b[s]
        else:
            step = 1 / 3 if r == 2 / 3 else 0.5 if r == 0.5 else 1.0   # 2/3 간격 구간은 1/3 박 단위로 시작할 수 있다
            c0 = float(np.round((b[s] - t0) / period / step) * step)
        c = c0 + np.concatenate([[0.0], np.cumsum(np.full(e - s, r))])
        count[s:e + 1] = c
        on_beat = np.abs(c - np.round(c)) < 1e-6
        known_k += list(np.round(c[on_beat]))
        known_t += list(b[s:e + 1][on_beat])
        if len(known_k) > 8:
            period, t0 = np.polyfit(known_k, known_t, 1)
    if t0 is None:
        raise ValueError(f"{bpm} BPM과 맞는 박 간격이 이어진 구간이 없습니다.")
    ok = ~np.isnan(count)
    k_all, t_all = count[ok], b[ok]
    order = np.argsort(k_all, kind="stable")
    k_all, t_all = k_all[order], t_all[order]
    keep = np.concatenate([[True], np.diff(k_all) > 0])
    k_all, t_all = k_all[keep], t_all[keep]
    new = np.interp(np.arange(np.ceil(k_all[0]), np.floor(k_all[-1]) + 1), k_all, t_all)
    downbeats = np.asarray(downbeats, dtype=float)
    if len(downbeats) == 0:
        return new, np.array([])
    per_bar = estimate_beats_per_bar(b, downbeats)
    first = int(np.argmin(np.abs(new - downbeats[0])))
    return new, new[first % per_bar::per_bar]


def beat_levels(beats: Sequence[float]) -> tuple[float, float]:
    """박 간격을 가장 많이 설명하는 한 박 길이 v와, 두 단위(v, v x 2/3) 중 적은 쪽의 비율.

    겹박자 곡에서 Beat This!는 점4분음표(v)와 8분음표 2개(v x 2/3)를 구간마다 바꿔 가며 박으로 잡는다.
    두 단위가 둘 다 많으면 겹박자일 가능성이 크다. 단순 박자 곡은 한쪽만 나와서 비율이 0에 가깝다.
    """
    iv = np.diff(np.asarray(beats, dtype=float))
    iv = iv[(iv > MIN_BEAT_INTERVAL) & (iv < MAX_BEAT_INTERVAL)]
    if len(iv) == 0:
        return 0.0, 0.0
    best_score, best_v = -1, 0.0
    for v in np.arange(0.25, 1.2, 0.0025):
        score = int((np.abs(iv / v - 1) < 0.08).sum() + (np.abs(iv / (v * 2 / 3) - 1) < 0.08).sum())
        if score > best_score:
            best_score, best_v = score, float(v)
    # 같은 점수가 이어지는 구간의 맨 앞 v가 잡히므로, 해당 간격들의 평균으로 다시 맞춘다
    one = np.abs(iv / best_v - 1) < 0.08
    two_thirds = np.abs(iv / (best_v * 2 / 3) - 1) < 0.08
    v = float(np.mean(np.concatenate([iv[one], iv[two_thirds] * 1.5])))
    one = np.abs(iv / v - 1) < 0.08
    two_thirds = np.abs(iv / (v * 2 / 3) - 1) < 0.08
    return v, float(min(one.mean(), two_thirds.mean()))


def triplet_share(positions: Sequence[float]) -> float:
    """박 위가 아닌 음 중, 셋잇단 자리까지 거리가 16분음표 자리까지 거리의 절반도 안 되는 음의 비율."""
    p = np.asarray(positions, dtype=float)
    frac = p - np.floor(p)
    off = frac[(frac > 1 / 24) & (frac < 23 / 24)]
    if len(off) == 0:
        return 0.0
    d16 = np.abs(off * SUBDIVISION - np.round(off * SUBDIVISION)) / SUBDIVISION
    d3 = np.abs(off * TRIPLET_SUBDIVISION - np.round(off * TRIPLET_SUBDIVISION)) / TRIPLET_SUBDIVISION
    return float(np.mean(d3 < d16 * 0.5))


def detect_compound(beats: Sequence[float], onsets: Sequence[float]) -> tuple[bool, float]:
    """겹박자(12/8, 6/8)인지와 점4분음표 기준 BPM을 돌려준다. (is_compound, dotted_quarter_bpm)

    11곡(4/4 10곡, 12/8 1곡)으로 정한 기준이다. 4/4 곡은 두 지표가 모두 0~6%, 12/8 곡은 46%·22%였다.
    """
    b = np.asarray(beats, dtype=float)
    if len(b) < 2 or len(onsets) == 0:
        return False, 0.0
    v, level = beat_levels(b)
    trip = triplet_share(np.interp(onsets, b, np.arange(len(b))))
    is_compound = level >= COMPOUND_MIN_LEVEL and trip >= COMPOUND_MIN_TRIPLET
    return is_compound, (60.0 / v if v else 0.0)


def drum_bar_phase(midi: pretty_midi.PrettyMIDI, beats: Sequence[float],
                   beats_per_bar: int) -> tuple[int, dict[int, float]]:
    """스네어가 2·4박(백비트), 킥이 1박에 가장 많이 오는 마디 시작 위치(박 번호 mod 마디당 박 수)와 위치별 점수.

    점수 = (2·4박에 온 스네어 비율) + 0.5 x (1박에 온 킥 비율). 4박이 아닌 마디는 2박째부터 짝수 박을 백비트로 본다.
    박 위에 온 킥·스네어가 없으면 ({}, 0)처럼 점수 없이 0을 돌려준다.
    """
    b = np.asarray(beats, dtype=float)
    drums = [n for inst in midi.instruments if inst.is_drum for n in inst.notes]

    def on_beat(pitches):
        t = np.array([n.start for n in drums if n.pitch in pitches])
        if len(t) == 0:
            return np.array([], dtype=int)
        p = np.interp(t, b, np.arange(len(b)))
        return np.round(p[np.abs(p - np.round(p)) < 0.15]).astype(int)

    kick, snare = on_beat(KICK_PITCHES), on_beat(SNARE_PITCHES)
    if len(kick) + len(snare) == 0:
        return 0, {}
    backbeats = list(range(1, beats_per_bar, 2))
    scores = {}
    for start in range(beats_per_bar):
        s = (snare - start) % beats_per_bar
        k = (kick - start) % beats_per_bar
        scores[start] = (np.isin(s, backbeats).mean() if len(s) else 0.0) + 0.5 * ((k == 0).mean() if len(k) else 0.0)
    return max(scores, key=scores.get), scores


def choose_triplet_beats(positions: Sequence[float]) -> set[int]:
    """음 시작 위치(박 단위)를 박별로 모아, 셋잇단 칸이 확실히 더 잘 맞는 박 번호를 돌려준다.

    박 위(정박)에 있는 음은 두 칸 모두에 맞으므로 판단에서 뺀다. 박 위가 아닌 음이
    TRIPLET_MIN_OFFBEAT개 이상이고, 셋잇단 칸 평균 오차가 16분음표 칸 오차의
    TRIPLET_MARGIN배보다 작을 때만 셋잇단으로 본다. 애매하면 16분음표.
    """
    by_beat: dict[int, list[float]] = {}
    for p in positions:
        k = int(np.floor(p + 1 / 24))           # 다음 박 직전 음은 다음 박으로
        frac = p - k
        if min(abs(frac), abs(1 - frac)) > 1 / 24:   # 정박 음 제외
            by_beat.setdefault(k, []).append(frac)
    out = set()
    for k, fr in by_beat.items():
        if len(fr) < TRIPLET_MIN_OFFBEAT:
            continue
        fr = np.array(fr)
        err16 = np.mean(np.abs(fr * SUBDIVISION - np.round(fr * SUBDIVISION))) / SUBDIVISION
        err3 = np.mean(np.abs(fr * TRIPLET_SUBDIVISION - np.round(fr * TRIPLET_SUBDIVISION))) / TRIPLET_SUBDIVISION
        if err3 < err16 * TRIPLET_MARGIN:
            out.add(k)
    return out


def align_pretty_midi(midi: pretty_midi.PrettyMIDI, beats: Sequence[float],
                      downbeats: Sequence[float], *, triplets: bool = False,
                      compound: bool | None = None,
                      downbeat_shift: int | None = None,
                      auto_meter: bool = True) -> tuple[pretty_midi.PrettyMIDI, AlignResult]:
    """PrettyMIDI 객체를 박에 맞춰 보정한 새 객체를 돌려준다.

    박자는 곡 전체에 하나만 쓴다 (다운비트 사이 박 수의 최빈값).
    triplets=True면 박마다 16분음표 칸과 셋잇단 8분음표 칸 중 하나를 골라 맞춘다.
    compound=True면 겹박자로 쓴다: 박(점4분음표)을 16분음표 6칸으로 맞추고, 박자표는
    (마디당 박 수 x 3)/8, MIDI 템포는 4분음표 기준이라 bpm x 1.5로 쓴다. 이때 triplets는 쓰지 않는다.
    downbeat_shift: Beat This!가 마디 첫 박을 다른 박에 찍었을 때 마디선을 박 단위로 옮긴다
    (+1 = 한 박 늦게, -1 = 한 박 일찍 시작).
    compound / downbeat_shift가 None이면 auto_meter=True일 때 자동으로 정한다
    (detect_compound, drum_bar_phase). auto_meter=False면 None은 False / 0으로 본다.
    """
    beats = np.asarray(beats, dtype=float)
    downbeats = np.asarray(downbeats, dtype=float)

    beats = np.unique(beats[np.isfinite(beats)])
    if len(beats) < 2:
        raise ValueError("박이 2개 미만입니다.")
    downbeats = downbeats[np.isfinite(downbeats)]

    if compound is None:
        compound = False
        if auto_meter:
            onsets = [n.start for inst in midi.instruments for n in inst.notes]
            found, dotted_bpm = detect_compound(beats, onsets)
            if found:
                beats, downbeats = fix_beats(beats, downbeats, dotted_bpm)
                compound = True

    bpm, median_interval = estimate_bpm(beats)
    beat_duration = 60.0 / bpm
    beats_per_bar = estimate_beats_per_bar(beats, downbeats)
    detected_offset = compute_beat_offset(beats, downbeats, beats_per_bar)
    if downbeat_shift is None:
        downbeat_shift = 0
        if auto_meter:
            start, scores = drum_bar_phase(midi, beats, beats_per_bar)
            current = (-detected_offset) % beats_per_bar
            if scores and scores[start] - scores[current] > PHASE_MIN_GAIN:
                shift = (start + detected_offset) % beats_per_bar
                downbeat_shift = shift - beats_per_bar if shift > beats_per_bar // 2 else shift
    beat_offset = (detected_offset - downbeat_shift) % beats_per_bar
    beat_index = np.arange(len(beats))

    def time_to_beat_position(t: float) -> float:
        if t < beats[0]:
            pos = (t - beats[0]) / median_interval
        elif t > beats[-1]:
            pos = len(beats) - 1 + (t - beats[-1]) / median_interval
        else:
            pos = float(np.interp(t, beats, beat_index))
        return pos + beat_offset

    triplet_beats: set[int] = set()
    if triplets and not compound:
        triplet_beats = choose_triplet_beats(
            [time_to_beat_position(n.start) for inst in midi.instruments for n in inst.notes])

    def quantize(t: float) -> float:
        pos = time_to_beat_position(t)
        sub = (COMPOUND_SUBDIVISION if compound else
               TRIPLET_SUBDIVISION if int(np.floor(pos + 1 / 24)) in triplet_beats else SUBDIVISION)
        q = round(pos * sub) / sub
        # 첫 박 이전 음표는 0초로 붙는다 (원래 노트북 동작과 동일)
        return max(0.0, q * beat_duration)

    out = pretty_midi.PrettyMIDI(initial_tempo=bpm * 1.5 if compound else bpm, resolution=RESOLUTION)
    note_count = 0
    for inst in midi.instruments:
        new_inst = pretty_midi.Instrument(program=inst.program, is_drum=inst.is_drum, name=inst.name)
        for note in inst.notes:
            start, end = quantize(note.start), quantize(note.end)
            if end <= start:  # 최소 16분음표 길이 보장 (셋잇단 박이면 셋잇단 8분음표)
                pos = time_to_beat_position(note.start)
                sub = (COMPOUND_SUBDIVISION if compound else
                       TRIPLET_SUBDIVISION if int(np.floor(pos + 1 / 24)) in triplet_beats else SUBDIVISION)
                end = start + beat_duration / sub
            new_inst.notes.append(pretty_midi.Note(velocity=note.velocity, pitch=note.pitch,
                                                   start=start, end=end))
            note_count += 1
        out.instruments.append(new_inst)

    # 분모는 4로 쓴다: Beat This!의 박이 4분음표인지 점4분음표인지(예: 6/8)는 구분하지 않는다
    if compound:   # 점4분음표 박 → n/8 (예: 4박 → 12/8, 2박 → 6/8)
        out.time_signature_changes.append(pretty_midi.TimeSignature(beats_per_bar * 3, 8, 0))
    else:
        out.time_signature_changes.append(pretty_midi.TimeSignature(beats_per_bar, 4, 0))
    return out, AlignResult(bpm=bpm, note_count=note_count, beat_offset=beat_offset,
                            beats_per_bar=beats_per_bar, triplet_beats=len(triplet_beats),
                            compound=compound, downbeat_shift=downbeat_shift)


def align_midi(midi_path: str | Path, out_path: str | Path, *,
               audio_path: str | Path | None = None,
               beats: Sequence[float] | None = None,
               downbeats: Sequence[float] | None = None,
               device: str = "auto", bpm: float | None = None,
               triplets: bool = False, compound: bool | None = None,
               downbeat_shift: int | None = None, auto_meter: bool = True) -> AlignResult:
    """MIDI 파일을 박에 맞춰 보정해 저장한다.

    audio_path를 주면 Beat This!로 박을 찾고, beats/downbeats를 주면 그대로 쓴다.
    bpm을 주면 fix_beats로 박을 그 템포로 다시 센다. triplets는 align_pretty_midi 참고.
    """
    if beats is None:
        if audio_path is None:
            raise ValueError("audio_path 또는 beats 중 하나는 필요합니다.")
        beats, downbeats = detect_beats(audio_path, device=device)
    downbeats = list(downbeats) if downbeats is not None else []
    if bpm:
        beats, downbeats = fix_beats(beats, downbeats, bpm)
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    aligned, result = align_pretty_midi(midi, beats, downbeats, triplets=triplets, compound=compound,
                                        downbeat_shift=downbeat_shift, auto_meter=auto_meter)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    aligned.write(str(out_path))
    return result


# ----------------------------------------------------------------------
# 3. 일괄 처리
# ----------------------------------------------------------------------
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
STRIP_SUFFIXES = ("__no_vocals",)  # Demucs 출력 이름 규칙: 원곡과 짝지을 때 무시


def song_key(name: str) -> str:
    """파일/폴더 이름 → 짝짓기용 곡 이름 (한글 NFC 정규화, __no_vocals 제거)"""
    name = unicodedata.normalize("NFC", name)
    for suffix in STRIP_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def collect_midis(midi_dir: str | Path) -> dict[str, Path]:
    """MIDI를 곡 이름별로 모은다.

    - midi_dir/곡.mid                     → 곡 이름 = 파일 이름
    - midi_dir/곡/muscriptor_large.mid    → 곡 이름 = 폴더 이름 (MuScriptor 출력 구조)
    """
    midi_dir = Path(midi_dir)
    found: dict[str, Path] = {}
    for f in sorted(midi_dir.rglob("*.mid")) + sorted(midi_dir.rglob("*.midi")):
        if "__MACOSX" in f.parts or f.name.startswith("._"):
            continue
        name = f.stem if f.parent == midi_dir else f.parent.name
        found.setdefault(song_key(name), f)
    return found


def collect_audio(audio_dir: str | Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for f in sorted(Path(audio_dir).rglob("*")):
        if f.suffix.lower() in AUDIO_EXTS and "__MACOSX" not in f.parts and not f.name.startswith("._"):
            found.setdefault(song_key(f.stem), f)
    return found


def collect_beats(beats_dir: str | Path) -> dict[str, Path]:
    """곡_beats.json 또는 곡.json"""
    found: dict[str, Path] = {}
    for f in sorted(Path(beats_dir).glob("*.json")):
        stem = f.stem[: -len("_beats")] if f.stem.endswith("_beats") else f.stem
        found.setdefault(song_key(stem), f)
    return found


@dataclass
class BatchReport:
    succeeded: list[str]
    failed: dict[str, str]          # 곡 → 오류 메시지
    midi_only: list[str]            # 짝이 되는 오디오/박이 없는 MIDI
    source_only: list[str]          # 짝이 되는 MIDI가 없는 오디오/박


def align_batch(midi_dir: str | Path, out_dir: str | Path, *,
                audio_dir: str | Path | None = None,
                beats_dir: str | Path | None = None,
                device: str = "auto", auto_meter: bool = True, log=print) -> BatchReport:
    """폴더 단위로 보정한다. 곡 이름이 같은 MIDI와 오디오(또는 박 JSON)를 짝짓는다.

    출력: out_dir/곡_aligned.mid, 오디오로 박을 찾았다면 out_dir/곡_beats.json도 저장.
    한 곡이 실패해도 나머지는 계속 처리한다.
    """
    if (audio_dir is None) == (beats_dir is None):
        raise ValueError("audio_dir와 beats_dir 중 정확히 하나를 주세요.")
    midis = collect_midis(midi_dir)
    sources = collect_audio(audio_dir) if audio_dir else collect_beats(beats_dir)
    songs = sorted(set(midis) & set(sources))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = BatchReport([], {}, sorted(set(midis) - set(sources)), sorted(set(sources) - set(midis)))
    for i, song in enumerate(songs, 1):
        try:
            if audio_dir:
                beats, downbeats = detect_beats(sources[song], device=device)
                save_beats(out_dir / f"{song}_beats.json", beats, downbeats)
            else:
                beats, downbeats = load_beats(sources[song])
            r = align_midi(midis[song], out_dir / f"{song}_aligned.mid", beats=beats, downbeats=downbeats,
                           auto_meter=auto_meter)
            report.succeeded.append(song)
            shift = f" · bar shift {r.downbeat_shift:+d}" if r.downbeat_shift else ""
            log(f"[{i}/{len(songs)}] OK   {song} · BPM {r.bpm:.2f} · {r.meter} · notes {r.note_count}{shift}")
        except Exception as e:  # 한 곡 실패로 전체가 멈추지 않게
            report.failed[song] = str(e)
            log(f"[{i}/{len(songs)}] FAIL {song} · {e}")

    log(f"\n완료: 성공 {len(report.succeeded)} · 실패 {len(report.failed)} / 짝지어진 곡 {len(songs)}")
    if report.midi_only:
        log("짝이 없는 MIDI: " + ", ".join(report.midi_only))
    if report.source_only:
        log("짝이 없는 " + ("오디오" if audio_dir else "박 JSON") + ": " + ", ".join(report.source_only))
    return report


# ----------------------------------------------------------------------
# 4. CLI
# ----------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="MuScriptor MIDI를 Beat This! 박·다운비트에 맞춰 마디로 정리",
        epilog="한 곡: --midi --out (+ --audio 또는 --beats)\n"
               "여러 곡: --midi-dir --out-dir (+ --audio-dir 또는 --beats-dir)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    one = p.add_argument_group("한 곡")
    one.add_argument("--midi", help="입력 MIDI (MuScriptor 출력)")
    one.add_argument("--out", help="출력 MIDI 경로")
    one.add_argument("--audio", help="원곡 오디오 (Beat This!로 박 검출)")
    one.add_argument("--beats", help="미리 저장한 박 JSON ({beats, downbeats})")
    one.add_argument("--save-beats", help="검출한 박을 JSON으로 저장할 경로")
    many = p.add_argument_group("여러 곡 (일괄 처리)")
    many.add_argument("--midi-dir", help="MIDI 폴더 (곡.mid 또는 곡/muscriptor_large.mid)")
    many.add_argument("--out-dir", help="출력 폴더 (곡_aligned.mid, 곡_beats.json)")
    many.add_argument("--audio-dir", help="원곡 오디오 폴더 (곡.wav 등)")
    many.add_argument("--beats-dir", help="박 JSON 폴더 (곡_beats.json)")
    p.add_argument("--device", default="auto", help="auto | cuda | cpu (기본 auto)")
    p.add_argument("--bpm", type=float, help="곡의 실제 템포. 1.5배·2배·절반으로 찍힌 박을 이 템포로 다시 센다 (한 곡 모드)")
    p.add_argument("--triplets", action="store_true",
                   help="박마다 16분음표/셋잇단 8분음표 중 맞는 칸으로 정렬 (4/4 곡 안의 셋잇단, 한 곡 모드)")
    p.add_argument("--no-auto-meter", action="store_true",
                   help="자동 판별(12/8 감지, 드럼 기준 마디선)을 끈다")
    p.add_argument("--compound", action="store_true", default=None,
                   help="겹박자(6/8, 12/8): 박=점4분음표, 8분음표 3개로 나눠 정렬하고 n/8 박자표 (한 곡 모드). "
                        "--bpm은 점4분음표 기준 템포")
    p.add_argument("--downbeat-shift", type=int, default=None,
                   help="마디선을 박 단위로 옮김 (+1 한 박 늦게, -1 한 박 일찍). 마디 첫 박이 틀렸을 때 (한 곡 모드)")
    args = p.parse_args(argv)

    single = args.midi or args.out
    batch = args.midi_dir or args.out_dir
    if bool(single) == bool(batch):
        p.error("한 곡(--midi/--out)과 여러 곡(--midi-dir/--out-dir) 중 하나만 쓰세요.")

    if batch:
        if args.bpm or args.triplets or args.compound or args.downbeat_shift is not None:
            p.error("--bpm, --triplets, --compound, --downbeat-shift는 곡마다 다르게 정해야 해서 한 곡 모드에서만 씁니다.")
        if not (args.midi_dir and args.out_dir):
            p.error("--midi-dir와 --out-dir를 함께 주세요.")
        if bool(args.audio_dir) == bool(args.beats_dir):
            p.error("--audio-dir와 --beats-dir 중 하나만 주세요.")
        report = align_batch(args.midi_dir, args.out_dir, audio_dir=args.audio_dir,
                             beats_dir=args.beats_dir, device=args.device, auto_meter=not args.no_auto_meter)
        return 1 if report.failed else 0

    if not (args.midi and args.out):
        p.error("--midi와 --out을 함께 주세요.")
    if bool(args.audio) == bool(args.beats):
        p.error("--audio와 --beats 중 하나만 주세요.")
    if args.beats:
        beats, downbeats = load_beats(args.beats)
    else:
        beats, downbeats = detect_beats(args.audio, device=args.device)
        if args.save_beats:
            save_beats(args.save_beats, beats, downbeats)
    r = align_midi(args.midi, args.out, beats=beats, downbeats=downbeats, bpm=args.bpm,
                   triplets=args.triplets, compound=args.compound, downbeat_shift=args.downbeat_shift,
                   auto_meter=not args.no_auto_meter)
    extra = f" · triplet beats {r.triplet_beats}" if args.triplets and not r.compound else ""
    extra += f" · bar shift {r.downbeat_shift:+d}" if r.downbeat_shift else ""
    meter = f"{r.meter} (dotted quarter = {r.bpm:.2f})" if r.compound else r.meter
    print(f"BPM {r.bpm:.2f} · {meter} · notes {r.note_count} · beat offset {r.beat_offset}{extra} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
