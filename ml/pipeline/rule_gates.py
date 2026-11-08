#!/usr/bin/env python3
"""Rule-based checks on the separated BS-RoFormer stems. No model is loaded.

Two rules run inside unified.py:

1. Input check (right after BS-RoFormer). The song is rejected when it is too
   short, almost silent, or when the four band stems (drums, bass, guitar,
   piano) carry too little of the separated energy. A rejected song stops
   before MuScriptor, so the GPU Pod ends after separation (about 20 s).
2. Note gate (after MuScriptor, before merge_stems). Each transcribed note is
   kept only if its stem is loud enough around the note onset compared with
   the stem's own playing level. This removes notes MuScriptor writes from
   the small sound left in a stem while the instrument is resting.
   Notes of pitched stems are also cut where their stem stays quiet, since
   MuScriptor can hold the last note before a rest until the next onset
   (한 페이지가 될 수 있게: one note held for 11 s over bars 113-120).
   When the original lineup is unknown, a stem left with very few notes is
   then treated as absent. A declared instrument is never removed this way;
   it is reported as "faint" instead, so the app can warn about that part.

The thresholds were chosen from 14 band songs and 45 non-band files on
2026-11-09; see benchmarks/2026-11-09-rule-gates.md. Re-measure them with
measure_gates.py when the separator or transcription model changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf


STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")
BAND_STEMS = ("drums", "bass", "guitar", "piano")
EPS = 1e-12


@dataclass(frozen=True)
class GateConfig:
    # input check (benchmarks/2026-11-09-rule-gates.md)
    min_duration_sec: float = 30.0      # short percussive sound effects separate into drums
    min_level_dbfs: float = -50.0       # mean level of all six stems together
    min_band_ratio: float = 0.15        # band-stem energy / all-stem energy
    # note gate
    note_floor_db: float = -40.0        # note level relative to the stem's playing level
    note_abs_floor_dbfs: float = -65.0  # below this a note is dropped whatever the stem level
    reference_percentile: float = 99.0  # the stem's playing level: this percentile of frame power
    onset_window_sec: float = 0.2       # how long after the onset the level is read
    drum_window_sec: float = 0.08       # drum hits are short
    # note-end trim (pitched stems): a note ends where its stem stays quiet
    release_db: float = -30.0           # quiet = below this, relative to the stem's playing level
    release_hold_sec: float = 0.5       # ... for at least this long
    min_note_sec: float = 0.05          # a trimmed note keeps at least this length
    # sparse-stem rule, original lineup unknown only
    min_notes_per_minute: float = 20.0
    # two-guitar stereo check, original lineup unknown only: two guitars panned apart
    stereo_max_corr: float = 0.2        # median left/right correlation of 1 s windows below this ...
    stereo_max_balance: float = 0.17    # ... and median |L-R| energy balance below this -> two guitars
    hop: int = 1024

    def as_dict(self) -> dict:
        return asdict(self)


class InputRejected(Exception):
    """The uploaded audio does not look like a band song. `code` is for the app."""

    def __init__(self, code: str, message: str, detail: dict) -> None:
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


def db(power: float) -> float:
    return 10.0 * math.log10(max(power, EPS))


def frame_power(path: Path, hop: int) -> tuple[np.ndarray, int]:
    """Mean-square power of the mono mix-down per `hop` frames, read in blocks."""
    chunks: list[np.ndarray] = []
    with sf.SoundFile(str(path)) as audio:
        rate = audio.samplerate
        rest = np.zeros(0, dtype="float64")
        while True:
            block = audio.read(hop * 256, dtype="float32", always_2d=True)
            if not len(block):
                break
            mono = np.concatenate([rest, block.astype("float64").mean(axis=1)])
            usable = len(mono) // hop * hop
            if usable:
                chunks.append((mono[:usable].reshape(-1, hop) ** 2).mean(axis=1))
            rest = mono[usable:]
        if len(rest):
            chunks.append(np.array([(rest ** 2).mean()]))
    return (np.concatenate(chunks) if chunks else np.zeros(0)), rate


def check_input(stems_dir: Path, cfg: GateConfig) -> dict:
    """Return the measurements, or raise InputRejected."""
    powers = {name: frame_power(stems_dir / f"{name}.wav", cfg.hop) for name in STEMS}
    rate = powers["vocals"][1]
    frames = min(len(p) for p, _ in powers.values())
    duration = frames * cfg.hop / rate
    energy = {name: float(p[:frames].mean()) if frames else 0.0 for name, (p, _) in powers.items()}
    total = sum(energy.values())
    band_ratio = sum(energy[s] for s in BAND_STEMS) / total if total > EPS else 0.0
    report = {
        "duration_sec": round(duration, 2),
        "level_dbfs": round(db(total), 2),
        "band_ratio": round(band_ratio, 4),
        "stem_share": {name: round(value / total, 4) if total > EPS else 0.0
                       for name, value in energy.items()},
        "thresholds": {"min_duration_sec": cfg.min_duration_sec,
                       "min_level_dbfs": cfg.min_level_dbfs,
                       "min_band_ratio": cfg.min_band_ratio},
    }
    if duration < cfg.min_duration_sec:
        raise InputRejected("too_short", "The song is too short to make a score.", report)
    if db(total) < cfg.min_level_dbfs:
        raise InputRejected("silent", "The audio is almost silent.", report)
    if band_ratio < cfg.min_band_ratio:
        raise InputRejected("not_band_audio",
                            "Band instruments (drums, bass, guitar, keyboard) are barely audible.",
                            report)
    return report


def note_levels(notes: list[pretty_midi.Note], power: np.ndarray, rate: int, cfg: GateConfig,
                drums: bool) -> np.ndarray:
    """Loudest frame (dBFS) from one frame before each onset to the end of its window."""
    step = cfg.hop / rate
    window = cfg.drum_window_sec if drums else cfg.onset_window_sec
    levels = np.empty(len(notes))
    for i, note in enumerate(notes):
        first = max(0, int(note.start / step) - 1)
        length = min(window, max(note.end - note.start, step)) if not drums else window
        last = min(len(power), max(first + 2, int(math.ceil((note.start + length) / step)) + 1))
        segment = power[first:last]
        levels[i] = db(float(segment.max())) if len(segment) else db(0.0)
    return levels


def trim_note_ends(notes: list[pretty_midi.Note], power: np.ndarray, rate: int, ref_db: float,
                   cfg: GateConfig) -> tuple[int, float]:
    """End each note where the stem first stays below release_db for release_hold_sec.

    Only the note end moves; a note that is still sounding is left alone.
    Returns (trimmed notes, seconds removed).
    """
    if not len(power) or not notes:
        return 0, 0.0
    step = cfg.hop / rate
    quiet = 10.0 * np.log10(np.maximum(power, EPS)) - ref_db < cfg.release_db
    # run[i] = number of consecutive quiet frames starting at frame i
    run = np.zeros(len(quiet) + 1, dtype=int)
    for i in range(len(quiet) - 1, -1, -1):
        run[i] = run[i + 1] + 1 if quiet[i] else 0
    hold = max(1, int(math.ceil(cfg.release_hold_sec / step)))
    trimmed, removed = 0, 0.0
    for note in notes:
        first = int(math.ceil((note.start + cfg.min_note_sec) / step))
        last = min(len(quiet), int(note.end / step))
        if first >= last:
            continue
        hits = np.nonzero(run[first:last] >= hold)[0]
        if not len(hits):
            continue
        new_end = max(note.start + cfg.min_note_sec, (first + int(hits[0])) * step)
        if new_end < note.end - step:
            removed += note.end - new_end
            note.end = new_end
            trimmed += 1
    return trimmed, removed


def guitar_stereo(path: Path, cfg: GateConfig) -> dict:
    """Is the guitar stem two guitars panned to the two sides?

    Over 1 s windows where the stem plays (within 30 dB of its loudest),
    take the median left/right correlation and the median energy balance
    |L - R| / (L + R). Two guitars panned apart give a low correlation with
    balanced sides; one guitar panned to one side gives a low correlation
    but a large balance (Immigrant Song), and a centred guitar gives a high
    correlation. Thresholds: benchmarks/2026-11-09-rule-gates.md.
    """
    audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
    if audio.shape[1] < 2:
        return {"two_guitars": False, "reason": "mono"}
    n = len(audio) // rate
    if n == 0:
        return {"two_guitars": False, "reason": "too short"}
    left = audio[:n * rate, 0].astype("float64").reshape(n, rate)
    right = audio[:n * rate, 1].astype("float64").reshape(n, rate)
    el, er = (left ** 2).mean(axis=1), (right ** 2).mean(axis=1)
    energy = el + er
    active = energy > np.percentile(energy, 99) * 10 ** (-30 / 10)
    if active.sum() < 5:
        return {"two_guitars": False, "reason": "guitar barely sounds", "active_sec": int(active.sum())}
    corr = [float(np.corrcoef(a, b)[0, 1]) for a, b in zip(left[active], right[active])
            if a.std() > 0 and b.std() > 0]
    median_corr = float(np.median(corr)) if corr else 1.0
    balance = float(np.median(np.abs(el - er)[active] / energy[active]))
    two = median_corr < cfg.stereo_max_corr and balance < cfg.stereo_max_balance
    return {"two_guitars": bool(two), "corr": round(median_corr, 3), "balance": round(balance, 3),
            "active_sec": int(active.sum())}


def reference_level(power: np.ndarray, cfg: GateConfig) -> float:
    return db(float(np.percentile(power, cfg.reference_percentile))) if len(power) else db(0.0)


def family_tracks(midi: pretty_midi.PrettyMIDI, stem: str, family) -> list[pretty_midi.Instrument]:
    return [inst for inst in midi.instruments if family(inst) == stem]


def gate_stem(midi_path: Path, stem_wav: Path, stem: str, output: Path, cfg: GateConfig, family,
              *, declared: bool, original_unknown: bool, duration_sec: float) -> dict:
    """Write a gated copy of one stem MIDI and return what was kept and why.

    Only tracks of the stem's own family are gated; other tracks are copied
    unchanged (merge_stems drops them anyway).
    """
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    power, rate = frame_power(stem_wav, cfg.hop)
    ref = reference_level(power, cfg)
    tracks = family_tracks(midi, stem, family)
    before = sum(len(t.notes) for t in tracks)
    original_notes = {id(t): list(t.notes) for t in tracks}
    rel_all: list[float] = []
    for track in tracks:
        if not track.notes:
            continue
        levels = note_levels(track.notes, power, rate, cfg, drums=track.is_drum)
        rel = levels - ref
        rel_all.extend(rel.tolist())
        keep = (rel >= cfg.note_floor_db) & (levels >= cfg.note_abs_floor_dbfs)
        track.notes = [note for note, ok in zip(track.notes, keep) if ok]
    after = sum(len(t.notes) for t in tracks)
    report = {"reference_dbfs": round(ref, 2), "notes_before": before, "notes_after_gate": after,
              "dropped_quiet": before - after, "declared": declared, "action": "gated"}
    if declared and before and not after:
        # The user said this instrument is in the song: keep the ungated notes
        # rather than fail the song or leave the part empty.
        for track in tracks:
            track.notes = original_notes[id(track)]
        after = before
        report["action"] = "kept_ungated_declared"
    else:
        trimmed = removed = 0
        for track in tracks:
            if not track.is_drum:
                count, seconds = trim_note_ends(track.notes, power, rate, ref, cfg)
                trimmed += count
                removed += seconds
        report["trimmed_note_ends"] = trimmed
        report["trimmed_seconds"] = round(removed, 2)
    minutes = max(duration_sec, 1.0) / 60.0
    report["notes_per_minute"] = round(after / minutes, 2)
    # The user said the instrument is there but the stem barely sounds: the part
    # is still made, and the app warns that it may be empty or inaccurate.
    report["faint"] = bool(declared and (report["action"] == "kept_ungated_declared"
                                         or after / minutes < cfg.min_notes_per_minute))
    if original_unknown and after and after / minutes < cfg.min_notes_per_minute:
        for track in tracks:
            track.notes = []
        report["action"] = "dropped_sparse"
        after = 0
    report["notes_final"] = after
    if rel_all:
        report["relative_db_percentiles"] = {
            str(p): round(float(np.percentile(rel_all, p)), 2) for p in (1, 5, 10, 25, 50)}
    output.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(output))
    return report
