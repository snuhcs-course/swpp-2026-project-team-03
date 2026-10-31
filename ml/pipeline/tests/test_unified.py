from pathlib import Path
import json
import sys
from types import SimpleNamespace

import numpy as np
import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified import Runner, STEMS, TRANSCRIBE_STEMS, describe_tracks, merge_stem_midis, normalize_generated, present_parts, tab_ready  # noqa: E402


def instrument(program, name, *, drum=False):
    inst = pretty_midi.Instrument(program, is_drum=drum, name=name)
    inst.notes.append(pretty_midi.Note(100, 60 if not drum else 36, 0.0, 0.4))
    return inst


def test_merge_keeps_only_four_band_stems(tmp_path):
    programs = {"vocals": 29, "drums": 0, "bass": 33, "guitar": 29, "piano": 0, "other": 48}
    paths = {}
    for stem in STEMS:
        midi = pretty_midi.PrettyMIDI()
        midi.instruments.append(instrument(programs[stem], stem, drum=stem == "drums"))
        path = tmp_path / f"{stem}.mid"
        midi.write(str(path))
        paths[stem] = path
    out = tmp_path / "merged.mid"
    merged = merge_stem_midis(paths, out)
    assert out.is_file()
    assert len(STEMS) == 6 and len(TRANSCRIBE_STEMS) == 4
    assert len(merged.instruments) == 4
    assert sum(len(i.notes) for i in merged.instruments) == 4
    assert all(not i.name.startswith(("vocals:", "other:")) for i in merged.instruments)
    assert present_parts(merged) == {"piano", "guitar", "bass", "drums"}


def test_final_track_metadata_accepts_numpy_programs():
    midi = pretty_midi.PrettyMIDI()
    inst = instrument(33, "AI bass")
    inst.program = np.int64(33)
    midi.instruments.append(inst)
    assert json.loads(json.dumps(describe_tracks(midi))) == [
        {"name": "AI bass", "program": 33, "is_drum": False, "notes": 1}]


def test_generated_notes_are_clipped_to_song_duration(tmp_path):
    aligned = pretty_midi.PrettyMIDI(initial_tempo=90)
    aligned.time_signature_changes = [pretty_midi.TimeSignature(6, 8, 0)]
    raw = pretty_midi.PrettyMIDI(initial_tempo=90)
    inst = pretty_midi.Instrument(0)
    inst.notes = [pretty_midi.Note(100, 60, 1, 2),
                  pretty_midi.Note(100, 62, 11, 13),
                  pretty_midi.Note(100, 64, 13, 14)]
    raw.instruments.append(inst)
    source, output = tmp_path / "raw.mid", tmp_path / "normalized.mid"
    raw.write(str(source))
    stats = normalize_generated(source, "piano", aligned, 12, output)
    result = pretty_midi.PrettyMIDI(str(output))
    assert stats == {"raw_notes": 3, "kept_notes": 2, "dropped_after_end": 1,
                     "clipped_at_end": 1, "duration_sec": 12}
    assert result.get_end_time() == pytest.approx(12)
    assert [(x.numerator, x.denominator) for x in result.time_signature_changes] == [(6, 8)]


def test_tab_resume_requires_gp5_and_processed_midi(tmp_path):
    midi = tmp_path / "guitar.mid"
    gp5 = tmp_path / "song.gp5"
    midi.write_bytes(b"midi")
    assert not tab_ready(tmp_path, ("guitar.mid", "skyline_lead_rhythm.mid"))
    gp5.write_bytes(b"gp5")
    assert tab_ready(tmp_path, ("guitar.mid", "skyline_lead_rhythm.mid"))
    midi.unlink()
    assert not tab_ready(tmp_path, ("guitar.mid", "skyline_lead_rhythm.mid"))


def test_stage_failure_is_recorded_and_resume_checks_same_input(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "out", requested=[],
                           model="model", midigpt_model="yellow_medium", device="cpu",
                           beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable))
    runner = Runner(args)
    output = runner.out / "result.mid"
    with pytest.raises(RuntimeError, match="missing, empty, or invalid"):
        runner.stage("broken", [output], lambda: None)
    assert runner.manifest["status"] == "failed"
    assert "broken" not in runner.manifest["completed"]
    args.resume = True
    resumed = Runner(args)
    resumed.stage("broken", [output], lambda: output.write_bytes(b"midi"))
    assert "broken" in resumed.manifest["completed"]
    args.seed = 1
    with pytest.raises(ValueError, match="configuration differs"):
        Runner(args)
