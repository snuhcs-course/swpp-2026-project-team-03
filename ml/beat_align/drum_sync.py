"""ROCKY drum sync: 다른 악기의 음 시각을 드럼에 맞춰 바로잡는다 (박자 정렬 전 단계).

왜 필요한가
    MuScriptor는 오디오를 5초 조각으로 나눠 채보하는데, 분리된 stem(특히 기타)을 넣으면 한 조각 안에서
    음 시각을 점점 늦게(또는 이르게) 찍는 경우가 있다. Sweet Child O' Mine 30~35초 조각에서는
    기타가 드럼보다 최대 100 ms 늦었고, 박자 정렬의 16분음표 반올림에서 8분음표 화음이 엇박으로 넘어갔다.
    Demucs 드럼 MIDI는 거의 밀리지 않는다 (박에서 40 ms 넘게 벗어난 음 1.2%).

방법 (악기마다 따로, 드럼은 그대로)
    1. 각 음에서 가장 가까운 드럼 음을 찾고, 110 ms 안이면 "드럼과 같이 친 음"으로 본다.
    2. 각 음을 중심으로 앞뒤 2초(4초 구간) 안에서, 같이 친 음들의 (음 시각 - 드럼 시각) 중앙값을 그 음의 지연으로 본다.
    3. 같이 친 음이 3개보다 적으면 보정하지 않고, 보정 폭은 최대 100 ms로 자른다.
    4. 음의 시작과 끝을 지연만큼 옮긴다 (길이는 그대로).

    python drum_sync.py song.mid song_drumsync.mid

align.py는 기본으로 이 보정을 먼저 한 뒤 정렬한다 (--no-drum-sync로 끔).

Written with Claude (AI); reviewed by Soobin Jo.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pretty_midi

WINDOW = 4.0         # 지연을 재는 구간 길이 (초, 음을 가운데에 둔다)
MATCH_TOLERANCE = 0.11  # 드럼과 "같이 친 음"으로 보는 최대 거리 (초)
MIN_MATCHES = 3      # 구간 안에 같이 친 음이 이보다 적으면 보정하지 않는다
MAX_CORRECTION = 0.1  # 보정 폭 상한 (초)
REPORT_THRESHOLD = 0.02  # 이 이상 옮긴 음을 "보정된 음"으로 센다 (초)


@dataclass
class DrumSyncResult:
    drum_notes: int
    moved_notes: int      # REPORT_THRESHOLD 이상 옮긴 음 수
    max_shift: float      # 가장 크게 옮긴 폭 (초, 절댓값)


def local_lag(starts: Sequence[float], drum_starts: Sequence[float]) -> np.ndarray:
    """각 음의 지연(초). 양수 = 드럼보다 늦음. 근거가 부족하면 0."""
    st = np.asarray(starts, dtype=float)
    dr = np.asarray(sorted(set(drum_starts)), dtype=float)
    if len(dr) == 0 or len(st) == 0:
        return np.zeros(len(st))
    idx = np.searchsorted(dr, st)
    before = dr[np.clip(idx, 1, len(dr) - 1) - 1]
    after = dr[np.clip(idx, 0, len(dr) - 1)]
    lag = np.where(np.abs(st - before) < np.abs(st - after), st - before, st - after)
    matched = np.abs(lag) < MATCH_TOLERANCE
    out = np.zeros(len(st))
    for k, t in enumerate(st):
        near = matched & (np.abs(st - t) <= WINDOW / 2)
        if near.sum() >= MIN_MATCHES:
            out[k] = np.clip(np.median(lag[near]), -MAX_CORRECTION, MAX_CORRECTION)
    return out


def drum_sync(midi: pretty_midi.PrettyMIDI) -> DrumSyncResult:
    """드럼이 아닌 모든 트랙의 음을 드럼 기준 지연만큼 옮긴다 (midi를 직접 고친다)."""
    drums = [n.start for inst in midi.instruments if inst.is_drum for n in inst.notes]
    moved, max_shift = 0, 0.0
    for inst in midi.instruments:
        if inst.is_drum or not inst.notes:
            continue
        shift = local_lag([n.start for n in inst.notes], drums)
        for note, d in zip(inst.notes, shift):
            note.start = max(0.0, note.start - d)
            note.end = max(note.start + 0.01, note.end - d)
        moved += int((np.abs(shift) >= REPORT_THRESHOLD).sum())
        max_shift = max(max_shift, float(np.abs(shift).max()) if len(shift) else 0.0)
    return DrumSyncResult(drum_notes=len(drums), moved_notes=moved, max_shift=max_shift)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="다른 악기의 음 시각을 드럼에 맞춰 바로잡는다 (박자 정렬 전)")
    p.add_argument("midi", help="입력 MIDI (악기별 MuScriptor 결과를 합친 것)")
    p.add_argument("out", help="출력 MIDI")
    args = p.parse_args(argv)
    midi = pretty_midi.PrettyMIDI(args.midi)
    r = drum_sync(midi)
    midi.write(args.out)
    print(f"drum notes {r.drum_notes} · moved {r.moved_notes} notes (>= 20 ms) · max {r.max_shift * 1000:.0f} ms → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
