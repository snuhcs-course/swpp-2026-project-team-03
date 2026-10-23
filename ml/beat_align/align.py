"""ROCKY beat alignment.

MuScriptor가 기본 120 BPM 그리드로 써 준 MIDI를 Beat This!가 찾은
실제 박/다운비트 위에 다시 올려, 템포 하나 + 박자 하나의 마디로 정리한다.
박자(마디당 박 수)는 다운비트 사이의 박 수 중 가장 많이 나온 값으로 정한다.

    python align.py --midi song.mid --audio song.wav --out song_aligned.mid
    python align.py --midi-dir midi/ --audio-dir audio/ --out-dir aligned/

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
RESOLUTION = 480


@dataclass
class AlignResult:
    bpm: float
    note_count: int
    beat_offset: int
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR


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
    """박 간격의 중앙값으로 BPM을 구한다. (bpm, 중앙 간격 초)"""
    intervals = np.diff(beats)
    valid = intervals[(intervals > MIN_BEAT_INTERVAL) & (intervals < MAX_BEAT_INTERVAL)]
    if len(valid) == 0:
        raise ValueError("유효한 박 간격이 없습니다.")
    median_interval = float(np.median(valid))
    return 60.0 / median_interval, median_interval


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


def align_pretty_midi(midi: pretty_midi.PrettyMIDI, beats: Sequence[float],
                      downbeats: Sequence[float]) -> tuple[pretty_midi.PrettyMIDI, AlignResult]:
    """PrettyMIDI 객체를 박에 맞춰 보정한 새 객체를 돌려준다.

    박자는 곡 전체에 하나만 쓴다 (다운비트 사이 박 수의 최빈값).
    """
    beats = np.asarray(beats, dtype=float)
    downbeats = np.asarray(downbeats, dtype=float)

    beats = np.unique(beats[np.isfinite(beats)])
    if len(beats) < 2:
        raise ValueError("박이 2개 미만입니다.")
    downbeats = downbeats[np.isfinite(downbeats)]

    bpm, median_interval = estimate_bpm(beats)
    beat_duration = 60.0 / bpm
    beats_per_bar = estimate_beats_per_bar(beats, downbeats)
    beat_offset = compute_beat_offset(beats, downbeats, beats_per_bar)
    beat_index = np.arange(len(beats))

    def time_to_beat_position(t: float) -> float:
        if t < beats[0]:
            pos = (t - beats[0]) / median_interval
        elif t > beats[-1]:
            pos = len(beats) - 1 + (t - beats[-1]) / median_interval
        else:
            pos = float(np.interp(t, beats, beat_index))
        return pos + beat_offset

    def quantize(t: float) -> float:
        q = round(time_to_beat_position(t) * SUBDIVISION) / SUBDIVISION
        # 첫 박 이전 음표는 0초로 붙는다 (원래 노트북 동작과 동일)
        return max(0.0, q * beat_duration)

    out = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=RESOLUTION)
    note_count = 0
    for inst in midi.instruments:
        new_inst = pretty_midi.Instrument(program=inst.program, is_drum=inst.is_drum, name=inst.name)
        for note in inst.notes:
            start, end = quantize(note.start), quantize(note.end)
            if end <= start:  # 최소 16분음표 길이 보장
                end = start + beat_duration / SUBDIVISION
            new_inst.notes.append(pretty_midi.Note(velocity=note.velocity, pitch=note.pitch,
                                                   start=start, end=end))
            note_count += 1
        out.instruments.append(new_inst)

    # 분모는 4로 쓴다: Beat This!의 박이 4분음표인지 점4분음표인지(예: 6/8)는 구분하지 않는다
    out.time_signature_changes.append(pretty_midi.TimeSignature(beats_per_bar, 4, 0))
    return out, AlignResult(bpm=bpm, note_count=note_count, beat_offset=beat_offset,
                            beats_per_bar=beats_per_bar)


def align_midi(midi_path: str | Path, out_path: str | Path, *,
               audio_path: str | Path | None = None,
               beats: Sequence[float] | None = None,
               downbeats: Sequence[float] | None = None,
               device: str = "auto") -> AlignResult:
    """MIDI 파일을 박에 맞춰 보정해 저장한다.

    audio_path를 주면 Beat This!로 박을 찾고, beats/downbeats를 주면 그대로 쓴다.
    """
    if beats is None:
        if audio_path is None:
            raise ValueError("audio_path 또는 beats 중 하나는 필요합니다.")
        beats, downbeats = detect_beats(audio_path, device=device)
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    aligned, result = align_pretty_midi(midi, beats, downbeats or [])
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
                device: str = "auto", log=print) -> BatchReport:
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
            r = align_midi(midis[song], out_dir / f"{song}_aligned.mid", beats=beats, downbeats=downbeats)
            report.succeeded.append(song)
            log(f"[{i}/{len(songs)}] OK   {song} · BPM {r.bpm:.2f} · {r.beats_per_bar}/4 · notes {r.note_count}")
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
    args = p.parse_args(argv)

    single = args.midi or args.out
    batch = args.midi_dir or args.out_dir
    if bool(single) == bool(batch):
        p.error("한 곡(--midi/--out)과 여러 곡(--midi-dir/--out-dir) 중 하나만 쓰세요.")

    if batch:
        if not (args.midi_dir and args.out_dir):
            p.error("--midi-dir와 --out-dir를 함께 주세요.")
        if bool(args.audio_dir) == bool(args.beats_dir):
            p.error("--audio-dir와 --beats-dir 중 하나만 주세요.")
        report = align_batch(args.midi_dir, args.out_dir, audio_dir=args.audio_dir,
                             beats_dir=args.beats_dir, device=args.device)
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
    r = align_midi(args.midi, args.out, beats=beats, downbeats=downbeats)
    print(f"BPM {r.bpm:.2f} · {r.beats_per_bar}/4 · notes {r.note_count} · beat offset {r.beat_offset} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
