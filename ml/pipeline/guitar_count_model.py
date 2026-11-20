"""Inference for the bundled four-score ExtraTrees rollback model.

The JSON stores tree parameters and needs no scikit-learn at runtime.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import pretty_midi


FEATURES = ("corr", "balance", "unplayable", "wide")
MODEL_ID = "guitar-count-extra-trees-4-v1"


def split_scores(aligned_guitar_midi: Path, guitar_code: Path) -> dict:
    """Extract split scores from the gated, beat-aligned guitar-only MIDI."""
    if str(guitar_code) not in sys.path:
        sys.path.insert(0, str(guitar_code))
    from skyline_tab import choose_tuning, decide_split, guitar_notes

    notes = guitar_notes(pretty_midi.PrettyMIDI(str(aligned_guitar_midi)))
    if not notes:
        raise ValueError("No gated guitar notes for guitar-count inference")
    tuning = choose_tuning([note.pitch for note in notes])
    _, stats = decide_split(notes, tuning)
    return {"tuning": tuning, **stats}


def load_model(path: Path) -> dict:
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("model_id") != MODEL_ID or tuple(model.get("features", ())) != FEATURES:
        raise ValueError("Unsupported guitar-count model or feature contract")
    if model.get("classes") != [1, 2] or not model.get("trees"):
        raise ValueError("Invalid guitar-count model")
    return model


def predict(model: dict, scores: dict) -> tuple[int, float]:
    """Return (guitar count, uncalibrated tree vote fraction for two guitars)."""
    values = [float(scores[key]) for key in FEATURES]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Guitar-count features must be finite")
    two = 0.0
    for tree in model["trees"]:
        node = 0
        while tree["feature"][node] >= 0:
            feature = tree["feature"][node]
            node = (tree["left"][node] if values[feature] <= tree["threshold"][node]
                    else tree["right"][node])
        two += float(tree["prob_two"][node])
    fraction = two / len(model["trees"])
    return (2 if fraction > 0.5 else 1), fraction
