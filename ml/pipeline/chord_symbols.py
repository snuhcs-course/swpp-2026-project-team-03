"""Estimate one chord symbol per measure (or half measure) from the final score MIDI.

Transcriptions contain stray notes, and a wrong chord is worse for a band than
none, so a window whose notes do not clearly fit one chord stays blank.
"""
from __future__ import annotations

import numpy as np

SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
FLAT_KEYS = {1, 3, 5, 6, 8, 10}  # Db, Eb, F, Gb, Ab, Bb major
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)

# suffix: {interval: weight}. Sevenths weigh less so a plain triad stays a triad.
QUALITIES = {
    "": {0: 1.0, 4: 0.8, 7: 0.8},
    "m": {0: 1.0, 3: 0.8, 7: 0.8},
    "5": {0: 1.0, 7: 0.8},
    "7": {0: 1.0, 4: 0.8, 7: 0.8, 10: 0.6},
    "maj7": {0: 1.0, 4: 0.8, 7: 0.8, 11: 0.6},
    "m7": {0: 1.0, 3: 0.8, 7: 0.8, 10: 0.6},
}
SEVENTH_PENALTY = 0.03
BASS_BONUS = 0.08
BASS_MAX_PITCH = 52
MIN_SIMILARITY = 0.80
MIN_MARGIN = 0.03
MIN_PITCH_CLASSES = 2
PITCH_CLASS_FLOOR = 0.10


def _templates() -> list[tuple[int, str, np.ndarray]]:
    out = []
    for root in range(12):
        for suffix, intervals in QUALITIES.items():
            vector = np.zeros(12)
            for interval, weight in intervals.items():
                vector[(root + interval) % 12] = weight
            out.append((root, suffix, vector / np.linalg.norm(vector)))
    return out


TEMPLATES = _templates()


def _note_table(midi) -> np.ndarray:
    rows = [(n.pitch, n.start, n.end, n.velocity / 127.0)
            for track in midi.instruments if not track.is_drum for n in track.notes]
    return np.asarray(rows, dtype=float).reshape(-1, 4)


def _chroma(notes: np.ndarray, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
    overlap = np.minimum(notes[:, 2], end) - np.maximum(notes[:, 1], start)
    active = overlap > 0
    pitches = notes[active, 0].astype(int)
    weights = overlap[active] * notes[active, 3]
    chroma = np.bincount(pitches % 12, weights=weights, minlength=12)
    low = pitches <= BASS_MAX_PITCH
    bass = np.bincount(pitches[low] % 12, weights=weights[low], minlength=12)
    return chroma, bass


def _classify(chroma: np.ndarray, bass: np.ndarray) -> tuple[int, str] | None:
    peak = chroma.max()
    if peak <= 0 or int((chroma >= peak * PITCH_CLASS_FLOOR).sum()) < MIN_PITCH_CLASSES:
        return None
    unit = chroma / np.linalg.norm(chroma)
    bass_root = int(bass.argmax()) if bass.max() > 0 else None
    scored = []
    for root, suffix, template in TEMPLATES:
        similarity = float(unit @ template)
        score = similarity - (SEVENTH_PENALTY if "7" in suffix else 0.0)
        score += BASS_BONUS if root == bass_root else 0.0
        scored.append((score, similarity, root, suffix))
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_similarity, best_root, best_suffix = scored[0]
    if best_similarity < MIN_SIMILARITY:
        return None
    rival = next((s for s, _, root, _ in scored[1:] if root != best_root), None)
    if rival is not None and best_score - rival < MIN_MARGIN:
        return None
    return best_root, best_suffix


def _spelling(notes: np.ndarray) -> tuple[str, ...]:
    weights = notes[:, 3] * np.maximum(notes[:, 2] - notes[:, 1], 0)
    chroma = np.bincount(notes[:, 0].astype(int) % 12, weights=weights, minlength=12)
    fit = [sum(chroma[(key + step) % 12] for step in MAJOR_SCALE) for key in range(12)]
    return FLAT_NAMES if int(np.argmax(fit)) in FLAT_KEYS else SHARP_NAMES


def estimate_chords(midi) -> dict[int, list[tuple[float, str]]]:
    """Return {0-based measure: [(position in measure 0..1, symbol), ...]}."""
    notes = _note_table(midi)
    if not len(notes):
        return {}
    names = _spelling(notes)
    downbeats = [float(t) for t in midi.get_downbeats()]
    downbeats.append(max(float(midi.get_end_time()), downbeats[-1]))
    chords: dict[int, list[tuple[float, str]]] = {}
    for index, (start, end) in enumerate(zip(downbeats, downbeats[1:])):
        if end <= start:
            continue
        middle = (start + end) / 2
        first = _classify(*_chroma(notes, start, middle))
        second = _classify(*_chroma(notes, middle, end))
        if first and second and first != second:
            found = [(0.0, first), (0.5, second)]
        else:
            whole = _classify(*_chroma(notes, start, end))
            found = [(0.0, whole)] if whole else []
        if found:
            chords[index] = [(position, names[root] + suffix) for position, (root, suffix) in found]
    return chords


def add_chords_to_track(track, chords: dict[int, list[tuple[float, str]]]) -> int:
    """Write chord names onto the first voice of a PyGuitarPro track."""
    from guitarpro import models

    written = 0
    for index, measure in enumerate(track.measures):
        beats = measure.voices[0].beats if measure.voices else []
        for position, name in chords.get(index, ()):
            target = measure.start + position * measure.length
            # A note held across the half-bar has no beat there: skip rather than misplace it.
            beat = next((b for b in beats if b.start == round(target)), None)
            if beat is None:
                continue
            chord = models.Chord(len(track.strings))
            chord.name = name
            chord.firstFret = 1
            chord.strings = [-1] * len(track.strings)
            beat.effect.chord = chord
            written += 1
    return written
