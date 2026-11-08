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
   When the original lineup is unknown, a stem left with very few notes is
   then treated as absent. A declared instrument is never removed this way.

All thresholds below are provisional. Measure them with measure_gates.py on
band and non-band audio before relying on them.
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
    # input check (provisional)
    min_duration_sec: float = 10.0
    min_level_dbfs: float = -50.0       # mean level of all six stems together
    min_band_ratio: float = 0.25        # band-stem energy / all-stem energy
    # note gate (provisional)
    note_floor_db: float = -30.0        # note level relative to the stem's playing level
    note_abs_floor_dbfs: float = -65.0  # below this a note is dropped whatever the stem level
    reference_percentile: float = 99.0  # the stem's playing level: this percentile of frame power
    onset_window_sec: float = 0.2       # how long after the onset the level is read
    drum_window_sec: float = 0.08       # drum hits are short
    # sparse-stem rule, original lineup unknown only (provisional)
    min_notes_per_minute: float = 6.0
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
    minutes = max(duration_sec, 1.0) / 60.0
    report["notes_per_minute"] = round(after / minutes, 2)
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
