"""Read model assignment from server-owned pipeline output, including failed jobs."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


ALPHA_ARMS = frozenset({"fusion_extra_trees", "fusion_rbf_svm", "fusion_stem_extra_trees"})


def _hash(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _probability(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 < value <= 1 else None


def model_assignment(run: Path, *, completed_only: bool = False) -> dict:
    """Return the assigned arm even when a job failed before it produced a score."""
    empty = {"assigned_model": None, "applied_model": None, "model_sha256": None,
             "model_manifest_sha256": None, "assignment_probability": None,
             "predicted_guitars": None, "experiment_eligible": None}
    try:
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(manifest, dict) or (completed_only and manifest.get("status") != "complete"):
        return empty
    config = manifest.get("config")
    if not isinstance(config, dict):
        return empty
    if config.get("requested_guitars") == 0:
        return empty
    result = manifest.get("guitar_count")
    classifier = config.get("guitar_count_classifier")
    if classifier == "alpha_three_arm":
        arm = config.get("guitar_count_arm")
        if not isinstance(arm, str) or arm not in ALPHA_ARMS:
            return empty
        record = {**empty, "assigned_model": arm,
                  "assignment_probability": _probability(config.get("guitar_count_arm_probability")),
                  "model_manifest_sha256": _hash(config.get("guitar_count_alpha_manifest_sha256"))}
        if not isinstance(result, dict) or result.get("assigned_arm") != arm:
            return record
        if result.get("method") == "rule_fallback" and result.get("experiment_eligible") is False:
            return {**record, "applied_model": "rule_fallback", "experiment_eligible": False}
        probability = _probability(result.get("assignment_probability"))
        model_hash = _hash(result.get("model_sha256"))
        count = result.get("count")
        if (result.get("method") == "alpha_three_arm" and result.get("experiment_eligible") is True
                and probability is not None and probability == record["assignment_probability"]
                and model_hash is not None and type(count) is int and count in (1, 2)):
            return {**record, "applied_model": arm, "model_sha256": model_hash,
                    "predicted_guitars": count, "experiment_eligible": True}
        return record

    if classifier == "extra_trees":
        record = {**empty, "assigned_model": "extra_trees"}
        if not isinstance(result, dict):
            return record
        if result.get("method") == "rule_fallback":
            return {**record, "applied_model": "rule_fallback"}
        model_hash = _hash(result.get("model_sha256"))
        count = result.get("count")
        if (result.get("method") == "guitar-count-extra-trees-4-v1" and model_hash is not None
                and type(count) is int and count in (1, 2)):
            return {**record, "applied_model": result["method"], "model_sha256": model_hash,
                    "predicted_guitars": count}
        return record
    if classifier == "rule":
        return {**empty, "assigned_model": "rule", "applied_model": "rule"}
    return empty


def rating_model(run: Path) -> dict:
    """Copy only a completed score's model identity into a rating row."""
    return model_assignment(run, completed_only=True)
