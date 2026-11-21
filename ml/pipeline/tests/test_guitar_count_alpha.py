"""Check the frozen alpha artifacts and job assignment contract."""

from pathlib import Path
import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guitar_count_alpha  # noqa: E402
import stem_audio_features  # noqa: E402
import unified  # noqa: E402


def test_frozen_models_load_and_predict_without_labels():
    directory = Path(guitar_count_alpha.__file__).parent / "guitar_count_alpha_models"
    artifacts = guitar_count_alpha.load_models(directory)
    assert tuple(artifacts) == guitar_count_alpha.ARMS
    blocks = {"rules": np.zeros(4), "muscriptor": np.zeros(2790),
              "roformer": np.zeros(512), "stem": np.zeros(4)}
    result = guitar_count_alpha.predictions(artifacts, blocks)
    assert set(result) == set(guitar_count_alpha.ARMS)
    assert all(value["count"] in (1, 2) for value in result.values())
    with pytest.raises(ValueError, match="muscriptor"):
        guitar_count_alpha.predictions(artifacts, {**blocks, "muscriptor": np.zeros(10)})


def test_alpha_assignment_survives_resume(tmp_path, monkeypatch):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    model_dir = Path(guitar_count_alpha.__file__).parent / "guitar_count_alpha_models"
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "out", original="unknown",
                           requested="guitar1", model="large", midigpt_model="yellow_medium",
                           device="cpu", beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), bsroformer_models_dir=tmp_path / "models",
                           bsroformer_lib_dir=tmp_path / "pylib",
                           guitar_count_classifier="alpha_three_arm", alpha_models_dir=model_dir)
    monkeypatch.setattr(unified.secrets, "randbelow", lambda limit: 1)
    first = unified.Runner(args)
    assert first.alpha_arm == guitar_count_alpha.ARMS[1]
    assert first.config["guitar_count_arm_probability"] == 1 / 3
    assert json.loads(first.manifest_path.read_text())["config"]["guitar_count_arm"] == first.alpha_arm
    args.resume = True
    monkeypatch.setattr(unified.secrets, "randbelow", lambda unused: pytest.fail("rerandomized retry"))
    resumed = unified.Runner(args)
    assert resumed.alpha_arm == first.alpha_arm


def alpha_args(tmp_path, audio, resume):
    model_dir = Path(guitar_count_alpha.__file__).parent / "guitar_count_alpha_models"
    return SimpleNamespace(audio=audio, output_dir=tmp_path / "out", original="unknown",
                           requested="guitar1", model="large", midigpt_model="yellow_medium",
                           device="cpu", beat_checkpoint="checkpoint", seed=0, resume=resume,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), bsroformer_models_dir=tmp_path / "models",
                           bsroformer_lib_dir=tmp_path / "pylib",
                           guitar_count_classifier="alpha_three_arm", alpha_models_dir=model_dir)


def test_failed_pre_alpha_run_restarts_with_a_new_assignment(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    out = tmp_path / "out"
    (out / "stems").mkdir(parents=True)
    (out / "stems" / "old.wav").write_bytes(b"old")
    (out / "manifest.json").write_text(json.dumps({
        "config": {"audio_sha256": unified.digest(audio), "pipeline_contract": 15},
        "completed": ["separate"], "status": "failed"}))
    resumed = unified.Runner(alpha_args(tmp_path, audio, True))
    assert resumed.alpha_arm in guitar_count_alpha.ARMS
    assert resumed.manifest["completed"] == []
    assert not (out / "stems").exists() and audio.is_file()


@pytest.mark.parametrize("old", [{"status": "complete", "same_audio": True},
                                 {"status": "failed", "same_audio": False}])
def test_other_pre_alpha_manifests_are_not_cleared(tmp_path, old):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.mid").write_bytes(b"keep")
    sha = unified.digest(audio) if old["same_audio"] else "0" * 64
    (out / "manifest.json").write_text(json.dumps({
        "config": {"audio_sha256": sha}, "completed": [], "status": old["status"]}))
    with pytest.raises(ValueError, match="original alpha assignment"):
        unified.Runner(alpha_args(tmp_path, audio, True))
    assert (out / "keep.mid").is_file()


def test_missing_alpha_model_directory_does_not_abort_before_rule_fallback(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "out", original="unknown",
                           requested="guitar1", model="large", midigpt_model="yellow_medium",
                           device="cpu", beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), bsroformer_models_dir=tmp_path,
                           bsroformer_lib_dir=tmp_path,
                           guitar_count_classifier="alpha_three_arm",
                           alpha_models_dir=tmp_path / "missing-models")
    runner = unified.Runner(args)
    assert runner.alpha_arm in guitar_count_alpha.ARMS
    assert runner.alpha_models_sha256 is None


@pytest.mark.parametrize("arm", guitar_count_alpha.ARMS)
def test_assigned_arm_alone_drives_guitar_count(tmp_path, monkeypatch, arm):
    directory = Path(guitar_count_alpha.__file__).parent / "guitar_count_alpha_models"
    mu, ro = tmp_path / "mu.npz", tmp_path / "ro.npz"
    np.savez_compressed(mu, feature=np.zeros(2790))
    np.savez_compressed(ro, feature=np.zeros(512))
    stem_calls = []
    monkeypatch.setattr(stem_audio_features, "extract", lambda unused: (
        stem_calls.append(True) or np.zeros(4)))
    runner = unified.Runner.__new__(unified.Runner)
    runner.alpha_arm = arm
    runner.alpha_models_dir = directory
    runner.guitar_scores = lambda *unused: (
        {"corr": 0.1, "balance": 0.2, "unplayable": 0.03, "wide": 0.04},
        {"unplayable": 0.03, "wide": 0.04})
    result = runner.classify_alpha(tmp_path / "guitar.mid", tmp_path / "beats.json",
                                   {"corr": 0.1, "balance": 0.2}, tmp_path,
                                   mu, ro, tmp_path / "guitar.wav")
    assert result["assigned_arm"] == arm
    assert result["experiment_eligible"] is True
    assert tuple(result["candidate_predictions"]) == (arm,)
    assert result["count"] == result["candidate_predictions"][arm]["count"]
    assert result["two_guitars"] is (result["count"] == 2)
    assert bool(stem_calls) is (arm == "fusion_stem_extra_trees")


@pytest.mark.parametrize("failure", ["roformer", "model"])
def test_alpha_failure_uses_rule_without_eligibility(tmp_path, failure):
    runner = unified.Runner.__new__(unified.Runner)
    runner.alpha_arm = guitar_count_alpha.ARMS[0]
    runner.out = tmp_path
    runner.audio = tmp_path / "song.wav"
    runner.pipeline = tmp_path
    runner.model_python = Path(sys.executable)
    runner.args = SimpleNamespace(bsroformer_models_dir=tmp_path, bsroformer_lib_dir=tmp_path)
    if failure == "roformer":
        runner.stage = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("missing model"))
    else:
        runner.stage = lambda *args, **kwargs: None
        runner.classify_alpha = lambda *args: (_ for _ in ()).throw(ValueError("invalid feature"))
    result = runner.classify_alpha_with_fallback(
        tmp_path / "guitar.mid", tmp_path / "beats.json",
        {"corr": 0.1, "two_guitars": False}, tmp_path,
        tmp_path / "logits.npz", tmp_path / "roformer.npz", tmp_path / "stem.wav")
    assert result["method"] == "rule_fallback"
    assert result["assigned_arm"] == runner.alpha_arm
    assert result["experiment_eligible"] is False
    assert result["two_guitars"] is False
    assert "error" in result


def test_tab_subprocess_uses_its_own_python_packages(tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir()
    runner = unified.Runner.__new__(unified.Runner)
    runner.out = tmp_path
    runner.tab_python = tmp_path / "tab-python"
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "model-only-deps"))
    received = []
    monkeypatch.setattr(unified.subprocess, "run", lambda *args, **kwargs: (
        received.append(kwargs.get("env")) or SimpleNamespace(returncode=0)))
    runner.command("guitar_tab", [str(runner.tab_python), "skyline_tab.py"])
    runner.command("model_stage", [str(tmp_path / "model-python"), "model.py"])
    assert "PYTHONPATH" not in received[0]
    assert received[1] is None and os.environ["PYTHONPATH"].endswith("model-only-deps")
