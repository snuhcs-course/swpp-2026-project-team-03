"""Frozen three-model guitar-count inference on a fixed feature contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np


ARMS = ("fusion_extra_trees", "fusion_rbf_svm", "fusion_stem_extra_trees")
RULE_NAMES = ("corr", "balance", "unplayable", "wide")
STEM_NAMES = ("pan_spread", "pan_two_sides", "pitch_polyphony", "pitch_lr_distance")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_models(directory: Path, arms: tuple[str, ...] = ARMS) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if tuple(manifest["arms"]) != ARMS or manifest["format_version"] != 1:
        raise ValueError("Unexpected alpha model manifest")
    if not arms or any(arm not in ARMS for arm in arms):
        raise ValueError("Unknown alpha model assignment")
    artifacts = {}
    for arm in arms:
        path = directory / f"{arm}.joblib"
        if digest(path) != manifest["arms"][arm]["sha256"]:
            raise ValueError(f"Alpha model digest mismatch: {arm}")
        artifact = joblib.load(path)
        if artifact["arm"] != arm or tuple(artifact["feature_names"]["rules"]) != RULE_NAMES:
            raise ValueError(f"Alpha model feature contract mismatch: {arm}")
        artifacts[arm] = artifact
    return artifacts


def vector(artifact: dict, blocks: dict[str, np.ndarray]) -> np.ndarray:
    output = []
    for name, parts in artifact["preprocess"].items():
        value = np.asarray(blocks[name], dtype=np.float64).reshape(1, -1)
        expected = {"rules": 4, "muscriptor": 2790, "roformer": 512, "stem": 4}[name]
        if value.shape != (1, expected) or not np.isfinite(value).all():
            raise ValueError(f"Invalid alpha feature block: {name}")
        value = parts[0].transform(value)
        if len(parts) == 3:
            value = parts[2].transform(parts[1].transform(value))
        output.append(value / np.sqrt(value.shape[1]))
    return np.concatenate(output, axis=1)


def predictions(artifacts: dict, blocks: dict[str, np.ndarray]) -> dict:
    result = {}
    for arm in artifacts:
        artifact = artifacts[arm]
        value = vector(artifact, blocks)
        classifier = artifact["classifier"]
        count = int(classifier.predict(value)[0])
        score = (float(classifier.decision_function(value)[0]) if arm == "fusion_rbf_svm"
                 else float(classifier.predict_proba(value)[0, 1]))
        if count not in (1, 2):
            raise ValueError("Alpha classifier predicted an unsupported guitar count")
        result[arm] = {"count": count, "score": round(score, 6),
                       "score_kind": "svm_margin" if arm == "fusion_rbf_svm"
                                     else "uncalibrated_tree_fraction"}
    return result
