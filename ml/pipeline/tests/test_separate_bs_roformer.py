"""Exercise the SW six-stem adapter without downloading the GPU checkpoint."""

import hashlib
from pathlib import Path
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import separate_bs_roformer as separator  # noqa: E402


def test_sw_adapter_normalizes_six_stems_and_nonvocal_mix(tmp_path, monkeypatch):
    models = tmp_path / "models"
    model = models / separator.MODEL_DIRECTORY
    model.mkdir(parents=True)
    ckpt = model / f"{separator.MODEL_BASENAME}.ckpt"
    config = model / f"{separator.MODEL_BASENAME}.yaml"
    ckpt.write_bytes(b"test checkpoint")
    config.write_bytes(b"test config")
    monkeypatch.setattr(separator, "CHECKPOINT_SHA256", hashlib.sha256(ckpt.read_bytes()).hexdigest())
    monkeypatch.setattr(separator, "CONFIG_SHA256", hashlib.sha256(config.read_bytes()).hexdigest())
    lib = tmp_path / "pylib"
    lib.mkdir()
    audio = tmp_path / "guitar_piano_song.wav"
    sf.write(str(audio), np.full((512, 2), 0.1, dtype="float32"), 8000, subtype="FLOAT")
    levels = {"vocals": 0.3, "drums": 0.4, "bass": 0.2,
              "guitar": 0.3, "piano": 0.2, "other": 0.2}
    calls = []

    def fake_inference(command, *, env, check):
        calls.append(command)
        assert command[:3] == [sys.executable, "-m", "bs_roformer.inference"]
        assert env["PYTHONPATH"].split(separator.os.pathsep)[0] == str(lib)
        input_dir = Path(command[command.index("--input_folder") + 1])
        output_dir = Path(command[command.index("--store_dir") + 1])
        assert [path.name for path in input_dir.iterdir()] == ["song.wav"]
        assert Path(command[command.index("--models_dir") + 1]) == models
        for stem, level in levels.items():
            sf.write(str(output_dir / f"song_{stem}.wav"),
                     np.full((512, 2), level, dtype="float32"), 8000, subtype="FLOAT")
        sf.write(str(output_dir / "song_instrumental.wav"),
                 np.zeros((512, 2), dtype="float32"), 8000, subtype="FLOAT")

    monkeypatch.setattr(separator.subprocess, "run", fake_inference)
    first, second = tmp_path / "first", tmp_path / "second"
    separator.separate(audio, first, models, lib)
    separator.separate(audio, second, models, lib)
    expected = {f"{stem}.wav" for stem in separator.STEMS} | {"no_vocals.wav"}
    assert {path.name for path in first.iterdir()} == expected
    assert len(calls) == 2 and separator.valid_stems(first)
    assert sf.info(str(first / "guitar.wav")).subtype == "FLOAT"
    mix, rate = sf.read(str(first / "no_vocals.wav"), dtype="float32", always_2d=True)
    assert rate == 8000 and float(np.max(np.abs(mix))) == pytest.approx(0.99, abs=1e-6)
    for name in expected:
        first_audio, _ = sf.read(str(first / name), dtype="float32", always_2d=True)
        second_audio, _ = sf.read(str(second / name), dtype="float32", always_2d=True)
        assert np.array_equal(first_audio, second_audio)
    raw_low = tmp_path / "raw_low"
    raw_low.mkdir()
    for stem, level in levels.items():
        sf.write(str(raw_low / f"song_{stem}.wav"),
                 np.full((512, 2), level * 0.1, dtype="float32"), 8000, subtype="FLOAT")
    target_low = tmp_path / "target_low"
    _, _, peak = separator.normalize_stems(raw_low, target_low)
    low_mix, _ = sf.read(str(target_low / "no_vocals.wav"), dtype="float32", always_2d=True)
    assert peak == pytest.approx(0.13, abs=1e-6)
    assert float(np.max(np.abs(low_mix))) == pytest.approx(0.13, abs=1e-6)


def test_sw_adapter_rejects_wrong_checkpoint_before_inference(tmp_path):
    models = tmp_path / "models"
    model = models / separator.MODEL_DIRECTORY
    model.mkdir(parents=True)
    (model / f"{separator.MODEL_BASENAME}.ckpt").write_bytes(b"wrong model")
    (model / f"{separator.MODEL_BASENAME}.yaml").write_bytes(b"wrong config")
    with pytest.raises(ValueError, match="checksum mismatch"):
        separator.verify_model(models)
