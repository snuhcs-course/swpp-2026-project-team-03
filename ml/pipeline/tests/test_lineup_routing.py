"""Exercise lineup routing across separation, transcription, TAB, GPT and assembly."""

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unified  # noqa: E402
from unified import Runner, STEMS  # noqa: E402


def one_track(part, start=0.0):
    score = pretty_midi.PrettyMIDI()
    program = {"piano": 0, "guitar": 26, "bass": 33, "drums": 0}[part]
    track = pretty_midi.Instrument(program, is_drum=part == "drums", name=part)
    track.notes.append(pretty_midi.Note(90, 36 if part == "drums" else 60, start, start + 0.3))
    score.instruments.append(track)
    return score


@pytest.mark.parametrize("original,requested,auto_split,expected_stems,expected_guitars,generated,workers,stereo_two", [
    ("keyboard,guitar1", "keyboard,guitar2", False, {"guitar", "piano"}, 2, True, 1, False),
    ("keyboard,guitar2", "guitar1", False, {"guitar", "piano"}, 1, False, 1, False),
    ("unknown", "guitar1", True, {"drums", "bass", "guitar", "piano"}, 1, False, 1, False),
    ("unknown", "guitar2", False, {"drums", "bass", "guitar", "piano"}, 2, True, 2, False),
    ("keyboard,drums", "guitar1", False, {"drums", "piano"}, 1, True, 1, False),
    # two guitars panned apart: the stereo check forces a split, no MIDI-GPT guitar
    ("unknown", "guitar2", False, {"drums", "bass", "guitar", "piano"}, 2, False, 1, True),
])
def test_lineup_routing_without_gpu(tmp_path, monkeypatch, original, requested, auto_split,
                                    expected_stems, expected_guitars, generated, workers, stereo_two):
    audio = tmp_path / "song.wav"
    sf.write(str(audio), np.zeros((16000, 2), dtype="float32"), 8000, subtype="FLOAT")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "run", original=original,
                           requested=requested, model="large", midigpt_model="yellow_medium",
                           device="cpu", beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path / "modules", model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), no_publish=True,
                           bsroformer_models_dir=tmp_path / "models",
                           bsroformer_lib_dir=tmp_path / "pylib",
                           transcription_workers=workers,
                           # one fixture note per stem would count as a sparse stem
                           min_notes_per_minute=0.0)

    def save_beats(path, beats, downbeats):
        Path(path).write_text(json.dumps({"beats": beats, "downbeats": downbeats}), encoding="utf-8")

    def load_beats(path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data["beats"], data["downbeats"]

    def align_midi(source, output, **kwargs):
        shutil.copyfile(source, output)
        return SimpleNamespace(bpm=120, meter="4/4", note_count=4,
                               drum_sync=SimpleNamespace(moved_notes=0))

    beat_inputs = []
    def detect_beats(path, **kwargs):
        beat_inputs.append(Path(path))
        return [0.0, 0.5, 1.0], [0.0]

    monkeypatch.setitem(sys.modules, "align", SimpleNamespace(
        detect_beats=detect_beats,
        save_beats=save_beats, load_beats=load_beats, align_midi=align_midi,
        snap_to_reference=lambda generated, reference: (generated, {"mode": "stub"})))

    def guitar_tracks(directory):
        directory = Path(directory)
        name = "skyline_lead_rhythm.mid" if (directory / "skyline_lead_rhythm.mid").exists() else "guitar.mid"
        return pretty_midi.PrettyMIDI(str(directory / name)).instruments

    def build(aligned, guitars, basses):
        output = pretty_midi.PrettyMIDI()
        output.instruments = guitars + basses + [track for track in aligned.instruments
                                                 if track.program not in range(24, 40)]
        return output

    monkeypatch.setitem(sys.modules, "full_score", SimpleNamespace(guitar_tracks=guitar_tracks, build=build))
    monkeypatch.setattr(unified, "guitar_stereo", lambda path, cfg: {"two_guitars": stereo_two})
    runner = Runner(args)
    commands = []

    def fake_command(stage, command, env=None):
        commands.append((stage, command))
        if stage == "bs_roformer":
            directory = Path(command[3])
            # audible stems longer than the input check's minimum, so the song is accepted
            for stem in (*STEMS, "no_vocals"):
                sf.write(str(directory / f"{stem}.wav"), np.full((8000 * 40, 2), 0.1, dtype="float32"),
                         8000, subtype="FLOAT")
        elif stage == "muscriptor_batch":
            jobs = json.loads(Path(command[command.index("--jobs-file") + 1]).read_text(encoding="utf-8"))
            for job in jobs:
                one_track(job["stem"]).write(job["output"])
        elif stage.startswith("muscriptor_"):
            one_track(stage.removeprefix("muscriptor_")).write(command[3])
        elif stage in {"guitar_tab", "guitar_compressed", "generated_guitar_tab"}:
            directory = Path(command[3])
            directory.mkdir(exist_ok=True)
            split = command[command.index("--split") + 1] if "--split" in command else "auto"
            two = split == "always" or (split == "auto" and auto_split)
            score = one_track("guitar")
            if two:
                score.instruments.append(one_track("guitar", 0.5).instruments[0])
            score.write(str(directory / ("skyline_lead_rhythm.mid" if two else "guitar.mid")))
            (directory / "guitar.gp5").write_bytes(b"fixture")
        elif stage in {"bass_tab", "generated_bass_tab"}:
            directory = Path(command[3])
            directory.mkdir(exist_ok=True)
            one_track("bass").write(str(directory / "bass.mid"))
            (directory / "bass.gp5").write_bytes(b"fixture")
        elif stage == "midigpt":
            targets = command[3:command.index("--out")]
            directory = Path(command[command.index("--out") + 1])
            directory.mkdir(exist_ok=True)
            for target in targets:
                one_track(target, 0.5).write(str(directory / f"aligned__+{target}_only.mid"))
        else:
            raise AssertionError(f"Unexpected stage: {stage}")

    monkeypatch.setattr(runner, "command", fake_command)
    result = pretty_midi.PrettyMIDI(str(runner.run()))
    assert sum(24 <= track.program <= 31 for track in result.instruments) == expected_guitars
    batch = [command for stage, command in commands if stage == "muscriptor_batch"]
    assert len(batch) == (1 if workers == 1 else 0)
    if workers > 1:
        assert {stage.removeprefix("muscriptor_") for stage, _ in commands
                if stage.startswith("muscriptor_")} == expected_stems
    jobs = [job for name in ("probe_jobs.json", "transcription_jobs.json")
            if (path := runner.out / "stem_midi" / name).is_file()
            for job in json.loads(path.read_text(encoding="utf-8"))]
    assert {job["stem"] for job in jobs} == expected_stems
    if batch:
        assert "--model" in batch[0] and batch[0][batch[0].index("--model") + 1] == "large"
    assert ("midigpt" in [stage for stage, _ in commands]) == generated
    separator_command = next(command for stage, command in commands if stage == "bs_roformer")
    assert "--mix-stems" not in separator_command
    assert beat_inputs == [runner.out / "stems" / "no_vocals.wav"]
    assert runner.manifest["beat_mix_stems"] == ["drums", "bass", "guitar", "piano", "other"]
    assert runner.manifest["generated_targets"] == (["guitar"] if generated else [])
    assert runner.manifest["faint_parts"] == []  # every fixture stem is audible
    if original == "unknown" and requested == "guitar1":
        assert "--split" not in next(command for stage, command in commands if stage == "guitar_tab")
        assert "--split" in next(command for stage, command in commands if stage == "guitar_compressed")
    if original == "unknown" and requested == "guitar2":
        command = next(command for stage, command in commands if stage == "guitar_tab")
        if stereo_two:
            assert command[command.index("--split") + 1] == "always"
            assert runner.manifest["guitar_stereo"] == {"two_guitars": True}
        else:
            assert "--split" not in command
    if original == "keyboard,drums":
        assert "guitar" not in {track.name.split(":")[0] for track in
                                pretty_midi.PrettyMIDI(str(runner.out / "aligned.mid")).instruments}
