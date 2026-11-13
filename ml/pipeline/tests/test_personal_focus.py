"""Solo practice (--personal): transcribe only the chosen stem when it is in the song."""

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
from unified import Runner, STEMS, cli  # noqa: E402


def one_track(part, start=0.0, notes=1):
    score = pretty_midi.PrettyMIDI()
    program = {"piano": 0, "guitar": 26, "bass": 33, "drums": 0}[part]
    track = pretty_midi.Instrument(program, is_drum=part == "drums", name=part)
    for i in range(notes):
        track.notes.append(pretty_midi.Note(90, 36 if part == "drums" else 60,
                                            start + i * 0.5, start + i * 0.5 + 0.3))
    score.instruments.append(track)
    return score


def run_personal(tmp_path, monkeypatch, requested, *, in_song, workers=1):
    audio = tmp_path / "song.wav"
    sf.write(str(audio), np.zeros((16000, 2), dtype="float32"), 8000, subtype="FLOAT")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "run", original="unknown",
                           requested=requested, personal=True, model="large",
                           midigpt_model="yellow_medium", device="cpu", beat_checkpoint="checkpoint",
                           seed=0, resume=False, modules_root=tmp_path / "modules",
                           model_python=Path(sys.executable), tab_python=Path(sys.executable),
                           no_publish=True, bsroformer_models_dir=tmp_path / "models",
                           bsroformer_lib_dir=tmp_path / "pylib", transcription_workers=workers,
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

    monkeypatch.setitem(sys.modules, "align", SimpleNamespace(
        detect_beats=lambda path, **kwargs: ([0.0, 0.5, 1.0], [0.0]),
        save_beats=save_beats, load_beats=load_beats, align_midi=align_midi,
        snap_to_reference=lambda generated, reference: (generated, {"mode": "stub"})))

    def guitar_tracks(directory):
        return pretty_midi.PrettyMIDI(str(Path(directory) / "guitar.mid")).instruments

    def build(aligned, guitars, basses):
        output = pretty_midi.PrettyMIDI()
        output.instruments = guitars + basses + [track for track in aligned.instruments
                                                 if track.program not in range(24, 40)]
        return output

    monkeypatch.setitem(sys.modules, "full_score", SimpleNamespace(guitar_tracks=guitar_tracks, build=build))
    monkeypatch.setattr(unified, "guitar_stereo", lambda path, cfg: {"two_guitars": False})
    runner = Runner(args)
    focus = next(iter(runner.requested_parts))
    commands = []

    def transcribe(stem, output):
        output = Path(output)
        if output.is_file() and output.stat().st_size:
            return  # --resume-existing
        # A stem with no notes is an instrument that is not in the song.
        one_track(stem, notes=1 if (stem != focus or in_song) else 0).write(str(output))

    def fake_command(stage, command, env=None):
        commands.append((stage, command))
        if stage == "bs_roformer":
            directory = Path(command[3])
            for stem in (*STEMS, "no_vocals"):
                sf.write(str(directory / f"{stem}.wav"), np.full((8000 * 40, 2), 0.1, dtype="float32"),
                         8000, subtype="FLOAT")
        elif stage == "muscriptor_batch":
            jobs = json.loads(Path(command[command.index("--jobs-file") + 1]).read_text(encoding="utf-8"))
            for job in jobs:
                transcribe(job["stem"], job["output"])
        elif stage.startswith("muscriptor_"):
            transcribe(stage.removeprefix("muscriptor_"), command[3])
        elif stage in {"guitar_tab", "generated_guitar_tab"}:
            directory = Path(command[3])
            directory.mkdir(exist_ok=True)
            one_track("guitar").write(str(directory / "guitar.mid"))
            (directory / "guitar.gp5").write_bytes(b"fixture")
        elif stage in {"bass_tab", "generated_bass_tab"}:
            directory = Path(command[3])
            directory.mkdir(exist_ok=True)
            one_track("bass").write(str(directory / "bass.mid"))
            (directory / "bass.gp5").write_bytes(b"fixture")
        elif stage == "midigpt":
            directory = Path(command[command.index("--out") + 1])
            directory.mkdir(exist_ok=True)
            for target in command[3:command.index("--out")]:
                one_track(target, 0.5).write(str(directory / f"aligned__+{target}_only.mid"))
        else:
            raise AssertionError(f"Unexpected stage: {stage}")

    monkeypatch.setattr(runner, "command", fake_command)
    result = pretty_midi.PrettyMIDI(str(runner.run()))
    return runner, commands, result, focus


def transcribed(commands):
    stems = [stage.removeprefix("muscriptor_") for stage, _ in commands
             if stage.startswith("muscriptor_") and stage != "muscriptor_batch"]
    for stage, command in commands:
        if stage == "muscriptor_batch":
            jobs = json.loads(Path(command[command.index("--jobs-file") + 1]).read_text(encoding="utf-8"))
            stems += [job["stem"] for job in jobs]
    return stems


@pytest.mark.parametrize("requested", ["bass", "keyboard", "drums", "guitar1"])
def test_instrument_in_the_song_is_the_only_stem_transcribed(tmp_path, monkeypatch, requested):
    runner, commands, result, focus = run_personal(tmp_path, monkeypatch, requested, in_song=True)
    assert transcribed(commands) == [focus]
    assert "midigpt" not in [stage for stage, _ in commands]
    assert runner.manifest["personal_focus"] == {"stem": focus, "in_song": True}
    assert runner.manifest["transcribe_stems"] == [focus]
    assert runner.manifest["generated_targets"] == []
    assert {unified.family(track) for track in result.instruments} == {focus}
    assert "focus_probe" in runner.manifest["completed"]


@pytest.mark.parametrize("workers", [1, 2])
def test_instrument_not_in_the_song_is_generated_from_the_other_stems(tmp_path, monkeypatch, workers):
    runner, commands, result, focus = run_personal(tmp_path, monkeypatch, "bass", in_song=False,
                                                   workers=workers)
    # the focus stem is transcribed once (the probe), then the other three
    assert sorted(transcribed(commands)) == ["bass", "drums", "guitar", "piano"]
    assert transcribed(commands)[0] == "bass"
    midigpt = next(command for stage, command in commands if stage == "midigpt")
    assert midigpt[3:midigpt.index("--out")] == ["bass"]
    assert runner.manifest["personal_focus"] == {"stem": "bass", "in_song": False}
    assert runner.manifest["transcribe_stems"] == ["drums", "bass", "guitar", "piano"]
    assert runner.manifest["generated_targets"] == ["bass"]
    assert {unified.family(track) for track in result.instruments} == {"bass"}


def test_personal_needs_one_instrument_and_unknown_original(tmp_path, capsys):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    for extra in (["--requested", "bass,drums"], ["--original", "bass", "--requested", "bass"]):
        with pytest.raises(SystemExit):
            cli([str(audio), str(tmp_path / "run"), "--personal", "--no-publish", *extra])
        assert "--personal" in capsys.readouterr().err
