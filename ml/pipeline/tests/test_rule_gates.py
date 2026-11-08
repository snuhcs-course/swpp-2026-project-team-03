"""Input check and note gate on synthetic stems (no model)."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rule_gates import GateConfig, InputRejected, STEMS, check_input, gate_stem  # noqa: E402
from unified import Runner, family  # noqa: E402

RATE = 8000


def tone(seconds, amplitude, freq=220.0):
    t = np.arange(int(seconds * RATE)) / RATE
    mono = (amplitude * np.sin(2 * np.pi * freq * t)).astype("float32")
    return np.stack([mono, mono], axis=1)


def write_stems(directory, levels, seconds=40.0):
    directory.mkdir(parents=True, exist_ok=True)
    for stem in STEMS:
        sf.write(str(directory / f"{stem}.wav"), tone(seconds, levels.get(stem, 0.0)), RATE, subtype="FLOAT")


def test_band_song_is_accepted(tmp_path):
    write_stems(tmp_path, {"vocals": 0.3, "drums": 0.3, "bass": 0.2, "guitar": 0.2, "piano": 0.1, "other": 0.05})
    report = check_input(tmp_path, GateConfig())
    assert report["band_ratio"] > 0.5
    assert set(report["stem_share"]) == set(STEMS)


@pytest.mark.parametrize("levels,seconds,code", [
    ({"vocals": 0.3, "other": 0.05, "guitar": 0.01}, 40.0, "not_band_audio"),  # speech / podcast
    ({"other": 0.2, "drums": 0.02}, 40.0, "not_band_audio"),                   # street noise
    ({"drums": 0.0005, "guitar": 0.0005}, 40.0, "silent"),
    ({"drums": 0.3, "guitar": 0.3}, 14.0, "too_short"),  # e.g. a 14 s axe sound effect
])
def test_non_band_input_is_rejected(tmp_path, levels, seconds, code):
    write_stems(tmp_path, levels, seconds)
    with pytest.raises(InputRejected) as info:
        check_input(tmp_path, GateConfig())
    assert info.value.code == code
    assert "band_ratio" in info.value.as_dict()["detail"]


def resting_guitar(tmp_path):
    """Guitar plays 0-10 s and rests 10-20 s; only a small residue is left in the stem."""
    audio = np.concatenate([tone(10, 0.3), tone(10, 0.001)])
    wav = tmp_path / "guitar.wav"
    sf.write(str(wav), audio, RATE, subtype="FLOAT")
    midi = pretty_midi.PrettyMIDI()
    track = pretty_midi.Instrument(29, name="guitar")
    track.notes = [pretty_midi.Note(90, 52, s, s + 0.5) for s in (1.0, 3.0, 5.0, 12.0, 14.0, 16.0)]
    midi.instruments.append(track)
    path = tmp_path / "guitar.mid"
    midi.write(str(path))
    return wav, path


def test_notes_in_a_resting_stem_are_dropped(tmp_path):
    wav, path = resting_guitar(tmp_path)
    out = tmp_path / "gated.mid"
    report = gate_stem(path, wav, "guitar", out, GateConfig(min_notes_per_minute=0), family,
                       declared=True, original_unknown=False, duration_sec=20)
    starts = [round(n.start, 1) for n in pretty_midi.PrettyMIDI(str(out)).instruments[0].notes]
    assert starts == [1.0, 3.0, 5.0]
    assert (report["notes_before"], report["dropped_quiet"], report["action"]) == (6, 3, "gated")
    assert report["faint"] is False


def test_note_held_into_a_rest_is_cut_where_the_stem_goes_quiet(tmp_path):
    # like 한 페이지가 될 수 있게: the last note before a rest is held until the next onset
    wav = tmp_path / "guitar.wav"
    sf.write(str(wav), np.concatenate([tone(4, 0.3), tone(10, 0.001), tone(4, 0.3)]), RATE, subtype="FLOAT")
    midi = pretty_midi.PrettyMIDI()
    track = pretty_midi.Instrument(29, name="guitar")
    track.notes = [pretty_midi.Note(90, 75, 3.0, 14.0),    # held 11 s, over the rest
                   pretty_midi.Note(90, 52, 14.5, 15.5)]  # sounding: left alone
    midi.instruments.append(track)
    midi.write(str(tmp_path / "guitar.mid"))
    out = tmp_path / "gated.mid"
    report = gate_stem(tmp_path / "guitar.mid", wav, "guitar", out, GateConfig(min_notes_per_minute=0), family,
                       declared=True, original_unknown=False, duration_sec=18)
    notes = sorted(pretty_midi.PrettyMIDI(str(out)).instruments[0].notes, key=lambda n: n.start)
    assert 3.9 < notes[0].end < 4.3          # cut where the stem goes quiet (4 s), not 14 s
    assert abs(notes[1].end - 15.5) < 0.01
    assert report["trimmed_note_ends"] == 1 and report["trimmed_seconds"] > 9


def test_drum_note_lengths_are_not_trimmed(tmp_path):
    wav = tmp_path / "drums.wav"
    sf.write(str(wav), np.concatenate([tone(2, 0.3), tone(6, 0.001)]), RATE, subtype="FLOAT")
    midi = pretty_midi.PrettyMIDI()
    track = pretty_midi.Instrument(0, is_drum=True, name="drums")
    track.notes = [pretty_midi.Note(90, 36, 1.0, 5.0)]
    midi.instruments.append(track)
    midi.write(str(tmp_path / "drums.mid"))
    out = tmp_path / "gated.mid"
    gate_stem(tmp_path / "drums.mid", wav, "drums", out, GateConfig(min_notes_per_minute=0), family,
              declared=True, original_unknown=False, duration_sec=8)
    assert abs(pretty_midi.PrettyMIDI(str(out)).instruments[0].notes[0].end - 5.0) < 0.01


def test_declared_instrument_is_never_emptied(tmp_path):
    wav = tmp_path / "piano.wav"
    sf.write(str(wav), tone(20, 0.0005), RATE, subtype="FLOAT")
    midi = pretty_midi.PrettyMIDI()
    track = pretty_midi.Instrument(0, name="piano")
    track.notes = [pretty_midi.Note(80, 60, 2.0, 3.0)]
    midi.instruments.append(track)
    midi.write(str(tmp_path / "piano.mid"))
    out = tmp_path / "gated.mid"
    report = gate_stem(tmp_path / "piano.mid", wav, "piano", out, GateConfig(), family,
                       declared=True, original_unknown=False, duration_sec=20)
    assert report["action"] == "kept_ungated_declared"
    assert report["faint"] is True
    assert len(pretty_midi.PrettyMIDI(str(out)).instruments[0].notes) == 1


def test_sparse_stem_is_absent_only_when_original_unknown(tmp_path):
    wav, path = resting_guitar(tmp_path)
    cfg = GateConfig(min_notes_per_minute=30)  # 3 kept notes in 20 s = 9 per minute
    unknown = gate_stem(path, wav, "guitar", tmp_path / "u.mid", cfg, family,
                        declared=False, original_unknown=True, duration_sec=20)
    known = gate_stem(path, wav, "guitar", tmp_path / "k.mid", cfg, family,
                      declared=True, original_unknown=False, duration_sec=20)
    assert (unknown["action"], unknown["notes_final"]) == ("dropped_sparse", 0)
    assert (known["action"], known["notes_final"]) == ("gated", 3)
    assert known["faint"] is True and unknown["faint"] is False


def test_rejection_is_recorded_in_manifest(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "out", requested=["guitar"],
                           model="model", midigpt_model="yellow_medium", device="cpu",
                           beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), bsroformer_models_dir=tmp_path / "models",
                           bsroformer_lib_dir=tmp_path / "pylib")
    runner = Runner(args)
    assert runner.config["rule_gates"]["min_band_ratio"] == GateConfig.min_band_ratio

    def refuse():
        raise InputRejected("not_band_audio", "nope", {"band_ratio": 0.01})

    with pytest.raises(InputRejected):
        runner.stage("input_check", [runner.out / "input_check.json"], refuse)
    assert runner.manifest["status"] == "rejected"
    assert runner.manifest["rejection"]["code"] == "not_band_audio"
    assert "input_check" not in runner.manifest["completed"]
