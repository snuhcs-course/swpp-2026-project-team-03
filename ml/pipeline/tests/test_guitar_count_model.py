"""Check the release model contract and its guitar-only feature path."""

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guitar_count_model  # noqa: E402
import unified  # noqa: E402


MODEL = Path(__file__).resolve().parents[1] / "guitar_count_extra_trees_v1.json"


def test_portable_model_has_four_finite_scores():
    model = guitar_count_model.load_model(MODEL)
    assert len(model["trees"]) == 300
    count, fraction = guitar_count_model.predict(
        model, {"corr": 0.1, "balance": 0.1, "unplayable": 0.02, "wide": 0.03})
    assert count in (1, 2) and 0 <= fraction <= 1
    with pytest.raises(ValueError, match="finite"):
        guitar_count_model.predict(model, {
            "corr": float("nan"), "balance": 0.1, "unplayable": 0.02, "wide": 0.03})


def test_guitar_only_alignment_for_release_features(tmp_path, monkeypatch):
    gated = tmp_path / "gated.mid"
    midi = pretty_midi.PrettyMIDI()
    for program, name in ((26, "guitar"), (0, "piano")):
        inst = pretty_midi.Instrument(program=program, name=name)
        inst.notes.append(pretty_midi.Note(90, 60, 0, 0.5))
        midi.instruments.append(inst)
    midi.write(str(gated))
    beats_file = tmp_path / "beats.json"
    beats_file.write_text(json.dumps({"beats": [0.0, 0.5], "downbeats": [0.0]}))
    calls = []

    def align(source, output, **kwargs):
        source_midi = pretty_midi.PrettyMIDI(str(source))
        calls.append((len(source_midi.instruments), kwargs["drum_sync"]))
        shutil.copyfile(source, output)

    monkeypatch.setitem(sys.modules, "align", SimpleNamespace(
        load_beats=lambda path: ([0.0, 0.5], [0.0]), align_midi=align))
    monkeypatch.setattr(guitar_count_model, "split_scores", lambda *unused: {
        "tuning": "standard", "onsets": 1, "unplayable": 0.02, "wide": 0.03})
    runner = unified.Runner.__new__(unified.Runner)
    runner.out = tmp_path
    runner.modules = tmp_path / "modules"
    runner.guitar_count_model = MODEL
    runner.guitar_count_model_sha256 = unified.digest(MODEL)
    result = runner.classify_guitars(gated, beats_file,
                                    {"corr": 0.1, "balance": 0.1}, tmp_path / "guitar_tab")
    expected, _ = guitar_count_model.predict(guitar_count_model.load_model(MODEL), result["scores"])
    assert calls == [(1, True)]
    assert result["count"] == expected
    assert result["vote_fraction_calibrated"] is False
    assert not list(tmp_path.glob("guitar-count-*"))


def test_unavailable_stereo_scores_use_rule_fallback(tmp_path):
    runner = unified.Runner.__new__(unified.Runner)
    report = runner.classify_guitars(tmp_path / "missing.mid", tmp_path / "missing.json",
                                     {"two_guitars": False, "reason": "mono"}, tmp_path)
    assert report == {"method": "rule_fallback", "reason": "stereo_scores_unavailable",
                      "two_guitars": False,
                      "stereo": {"two_guitars": False, "reason": "mono"}}
