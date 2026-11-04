from pathlib import Path
import json
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified import Runner, STEMS, TRANSCRIBE_STEMS, assemble, cli, describe_tracks, guitar_case, merge_stem_midis, merge_tracks, normalize_generated, parse_lineup, present_parts, tab_ready  # noqa: E402
from publish_scores import publication_ready, publish  # noqa: E402


def instrument(program, name, *, drum=False):
    inst = pretty_midi.Instrument(program, is_drum=drum, name=name)
    inst.notes.append(pretty_midi.Note(100, 60 if not drum else 36, 0.0, 0.4))
    return inst


def fake_score_export(cmd):
    target = Path(cmd[2] if cmd[0] == "musescore3" else cmd[3])
    if target.suffix == ".mscx":
        count = len([track for track in pretty_midi.PrettyMIDI(cmd[3]).instruments if track.notes])
        parts = "".join("<Part><trackName>old</trackName><Instrument><longName>old</longName>"
                        "<shortName>old</shortName><trackName>old</trackName></Instrument></Part>"
                        for _ in range(count))
        target.write_text(f"<museScore><Score>{parts}</Score></museScore>", encoding="utf-8")
    else:
        target.write_bytes((b"ID3" if target.suffix == ".mp3" else b"%PDF-1.7\n") + b"\0" * 1100)


def fake_gp5_score(source, target, parts, *, force=False):
    shutil.copyfile(source, target)


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


def test_piano_stem_tracks_become_one_piano_track(tmp_path):
    paths = {}
    for stem in STEMS:
        midi = pretty_midi.PrettyMIDI()
        if stem == "piano":
            for program, notes in ((0, [(60, 0.0, 1.0)]),
                                   (2, [(60, 0.02, 1.5), (64, 2.0, 3.0)]),
                                   (16, [(67, 4.0, 5.0)])):
                track = pretty_midi.Instrument(program)
                track.notes = [pretty_midi.Note(90, pitch, start, end)
                               for pitch, start, end in notes]
                midi.instruments.append(track)
            midi.instruments.append(instrument(26, "wrong guitar in piano stem"))
        else:
            midi.instruments.append(instrument({"drums": 0, "bass": 33}.get(stem, 29),
                                               stem, drum=stem == "drums"))
        path = tmp_path / f"{stem}.mid"
        midi.write(str(path))
        paths[stem] = path
    merged = merge_stem_midis(paths, tmp_path / "merged.mid")
    pianos = [track for track in merged.instruments if track.name.startswith("piano:")]
    assert [(track.name, track.program) for track in pianos] == [("piano: piano", 0)]
    assert [(note.pitch, note.start, note.end) for note in pianos[0].notes] == [
        (60, 0.0, 1.5), (64, 2.0, 3.0), (67, 4.0, 5.0)]
    assert len(merged.instruments) == 4
    assert present_parts(merged) == {"piano", "guitar", "bass", "drums"}


def test_merge_tracks_cuts_overlapping_same_pitch_and_keeps_retriggers():
    first, second = pretty_midi.Instrument(0), pretty_midi.Instrument(2)
    first.notes = [pretty_midi.Note(80, 60, 0.0, 2.0),
                   pretty_midi.Note(75, 60, 0.04, 1.5)]
    second.notes = [pretty_midi.Note(100, 60, 1.0, 3.0)]
    out = merge_tracks([first, second], 0, "piano: piano")
    assert [(note.start, note.end) for note in out.notes] == [
        (0.0, 0.04), (0.04, 1.0), (1.0, 3.0)]


def test_user_lineups_and_four_guitar_cases():
    assert parse_lineup("unknown", original=True) == (set(), 0, True)
    assert parse_lineup("keyboard,bass,guitar2,drums", original=True) == (
        {"piano", "bass", "guitar", "drums"}, 2, False)
    assert parse_lineup("keyboard,guitar1", original=False) == ({"piano", "guitar"}, 1, False)
    assert guitar_case(2, 2) == ("always", False)
    assert guitar_case(2, 1) == ("never", False)
    assert guitar_case(1, 1) == ("never", False)
    assert guitar_case(1, 2) == ("never", True)
    assert guitar_case(0, 1) == (None, True)
    with pytest.raises(ValueError, match="not supported"):
        guitar_case(0, 2)
    with pytest.raises(ValueError, match="exactly one guitar count"):
        parse_lineup("guitar1,guitar2", original=False)


def test_known_absent_stems_are_not_merged_or_used_as_gpt_context(tmp_path):
    paths = {}
    for stem, program in (("drums", 0), ("bass", 33), ("guitar", 26), ("piano", 0)):
        midi = pretty_midi.PrettyMIDI()
        midi.instruments.append(instrument(program, stem, drum=stem == "drums"))
        if stem == "piano":
            midi.instruments.append(instrument(26, "wrong guitar in piano stem"))
        paths[stem] = tmp_path / f"{stem}.mid"
        midi.write(str(paths[stem]))
    merged = merge_stem_midis(paths, tmp_path / "merged.mid", ("drums", "piano"))
    assert present_parts(merged) == {"drums", "piano"}
    assert len(merged.instruments) == 2


def test_additional_guitar_stays_separate_and_unrequested_part_is_removed(tmp_path, monkeypatch):
    aligned = pretty_midi.PrettyMIDI()
    aligned.instruments = [instrument(26, "original guitar"), instrument(0, "piano context")]
    aligned_path = tmp_path / "aligned.mid"
    aligned.write(str(aligned_path))
    original_dir, generated_dir = tmp_path / "guitar", tmp_path / "guitar_generated"
    original_dir.mkdir()
    generated_dir.mkdir()
    first = pretty_midi.PrettyMIDI()
    first.instruments = [instrument(26, "original processed")]
    first.write(str(original_dir / "guitar.mid"))
    second = pretty_midi.PrettyMIDI()
    second.instruments = [instrument(29, "new processed")]
    second.write(str(generated_dir / "guitar.mid"))
    generated_path = tmp_path / "generated_guitar.mid"
    second.write(str(generated_path))

    def fake_build(source, guitars, basses):
        score = pretty_midi.PrettyMIDI()
        score.instruments = guitars + basses + [i for i in source.instruments if i.program == 0]
        return score

    monkeypatch.setitem(sys.modules, "full_score", SimpleNamespace(
        build=fake_build,
        guitar_tracks=lambda directory: pretty_midi.PrettyMIDI(str(Path(directory) / "guitar.mid")).instruments))
    output = tmp_path / "full_score.mid"
    result = assemble(aligned_path, original_dir, tmp_path / "bass", {"guitar": generated_path},
                      output, tmp_path, {"guitar"}, generated_dir)
    assert output.is_file()
    assert len(result.instruments) == 2
    assert all(i.program in range(24, 32) for i in result.instruments)
    assert "AI generated" not in result.instruments[0].name
    assert "AI generated" in result.instruments[1].name


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
                           tab_python=Path(sys.executable), bsroformer_models_dir=tmp_path / "models",
                           bsroformer_lib_dir=tmp_path / "pylib")
    runner = Runner(args)
    assert runner.config["pipeline_contract"] == 10
    assert runner.config["beat_mix_stems"] == ["drums", "bass", "guitar", "piano", "other"]
    assert runner.config["separator"].endswith("BS-RoFormer-SW-6stem")
    output = runner.out / "result.mid"
    with pytest.raises(RuntimeError, match="missing, empty, or invalid"):
        runner.stage("broken", [output], lambda: None)
    assert runner.manifest["status"] == "failed"
    assert runner.manifest["stage_seconds"]["broken"] >= 0
    assert "broken" not in runner.manifest["completed"]
    args.resume = True
    resumed = Runner(args)
    resumed.stage("broken", [output], lambda: output.write_bytes(b"midi"))
    assert "broken" in resumed.manifest["completed"]
    assert resumed.manifest["stage_seconds"]["broken"] >= 0
    args.seed = 1
    with pytest.raises(ValueError, match="configuration differs"):
        Runner(args)
    args.seed = 0
    old_manifest = json.loads(runner.manifest_path.read_text(encoding="utf-8"))
    old_manifest["config"]["pipeline_contract"] = 8
    runner.manifest_path.write_text(json.dumps(old_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="configuration differs"):
        Runner(args)


def test_publication_adds_demo_audio_and_scores_to_completed_run(tmp_path, monkeypatch):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "run", requested=[],
                           model="model", midigpt_model="yellow_medium", device="cpu",
                           beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), musescore="musescore3",
                           node="node", gp5_converter=tmp_path / "convert.js", pdfinfo="pdfinfo",
                           bsroformer_models_dir=tmp_path / "models", bsroformer_lib_dir=tmp_path / "pylib")
    args.gp5_converter.write_text("// stub", encoding="utf-8")
    runner = Runner(args)
    score = pretty_midi.PrettyMIDI(initial_tempo=110)
    for program, name, drum in ((26, "Guitar", False), (33, "Bass", False),
                                (0, "piano: acoustic piano", False),
                                (2, "piano: electric piano", False),
                                (16, "piano: organ", False), (0, "drums: drums", True)):
        score.instruments.append(instrument(program, name, drum=drum))
    score.write(str(runner.out / "full_score.mid"))
    for part in ("guitar", "bass"):
        directory = runner.out / part
        directory.mkdir()
        (directory / f"{part}.gp5").write_bytes(b"GP5 fixture")
    runner.manifest["status"] = "complete"
    runner.manifest["completed"] = ["assemble"]
    runner.manifest_path.write_text(json.dumps(runner.manifest), encoding="utf-8")

    calls = []

    def fake_converter(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "pdfinfo":
            return subprocess.CompletedProcess(cmd, 0, stdout="Pages: 1\n")
        fake_score_export(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("publish_scores.subprocess.run", fake_converter)
    monkeypatch.setattr("publish_scores.shutil.which", lambda executable: executable)
    monkeypatch.setattr("publish_scores.gp5_score", fake_gp5_score)
    runner.publish_outputs()
    contract = json.loads((runner.out / "scores" / "score_outputs.json").read_text(encoding="utf-8"))
    assert contract["version"] == 4
    assert contract["audio"]["full_band"]["mp3"] == "scores/band.mp3"
    assert set(contract["audio"]["instruments"]) == {"guitar", "bass", "piano", "drums"}
    assert contract["audio"]["instruments"]["guitar"]["source"] == "scores/guitar.mid"
    assert contract["audio"]["full_band"]["source"] == "scores/band.mid"
    assert [track.program for track in pretty_midi.PrettyMIDI(str(runner.out / "scores" / "guitar.mid")).instruments] == [26]
    assert [track.program for track in pretty_midi.PrettyMIDI(str(runner.out / "scores" / "bass.mid")).instruments] == [33]
    assert [track.program for track in pretty_midi.PrettyMIDI(str(runner.out / "scores" / "band.mid")).instruments] == [26, 33, 0, 2, 16, 0]
    names = [part.findtext("Instrument/longName") for part in
             ET.parse(runner.out / "scores" / "full_band_render.mscx").getroot().findall("Score/Part")]
    assert names == ["Electric Guitar", "Electric Bass", "Piano", "Electric Piano", "Organ", "Drum Set"]
    assert set(contract["instruments"]) == {"guitar", "bass", "piano", "drums"}
    assert all((runner.out / "scores" / f"{part}.mid").is_file()
               for part in ("guitar", "bass", "piano", "drums"))
    assert len([cmd for cmd in calls if cmd[0] == "node"]) == 2
    assert len([cmd for cmd in calls if cmd[0] == "musescore3" and cmd[2].endswith(".pdf")]) == 3
    assert len([cmd for cmd in calls if cmd[0] == "musescore3" and cmd[2].endswith(".mp3")]) == 5
    assert publication_ready(runner.out)
    assert runner.manifest["status"] == runner.manifest["score_publication"] == "complete"

    (runner.out / "scores" / "guitar.mp3").unlink()
    assert not publication_ready(runner.out)
    args.resume = True
    resumed = Runner(args)
    calls.clear()
    resumed.publish_outputs()
    assert publication_ready(resumed.out)
    assert [Path(cmd[2]).name for cmd in calls if cmd[0] == "musescore3"] == ["guitar.mp3"]
    assert not any(cmd[0] == "node" for cmd in calls)

    (resumed.out / "guitar" / "guitar.gp5").write_bytes(b"corrected GP5")
    assert not publication_ready(resumed.out)
    calls.clear()
    Runner(args).publish_outputs()
    assert publication_ready(resumed.out)
    assert [Path(cmd[3]).name for cmd in calls if cmd[0] == "node"] == ["guitar.pdf"]


def test_auto_publication_checks_tools_before_creating_run(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    output = tmp_path / "run"
    with pytest.raises(FileNotFoundError, match="MuseScore executable not found"):
        cli([str(audio), str(output), "--requested", "keyboard",
             "--musescore", "missing-rocky-musescore-executable"])
    assert not output.exists()


def test_publication_uses_bounded_parallel_exports(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    score = pretty_midi.PrettyMIDI()
    score.instruments.append(instrument(0, "piano: piano"))
    score.write(str(run / "full_score.mid"))
    (run / "manifest.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    active = peak = 0
    lock = threading.Lock()

    def converter(cmd, **kwargs):
        nonlocal active, peak
        if cmd[0] == "pdfinfo":
            return subprocess.CompletedProcess(cmd, 0, stdout="Pages: 1\n")
        target = Path(cmd[2])
        if target.suffix in {".pdf", ".mp3"}:
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
        try:
            fake_score_export(cmd)
        finally:
            if target.suffix in {".pdf", ".mp3"}:
                with lock:
                    active -= 1
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("publish_scores.subprocess.run", converter)
    monkeypatch.setattr("publish_scores.shutil.which", lambda executable: executable)
    result = publish(run, "musescore3", "node", tmp_path / "unused.js", "pdfinfo",
                     force=False, render_workers=2)
    assert peak == 2
    assert set(result["instruments"]) == {"piano"}
    assert publication_ready(run)
    serial = publish(run, "musescore3", "node", tmp_path / "unused.js", "pdfinfo",
                     force=True, render_workers=1)
    assert result == serial
    real_ready = publication_ready
    readiness_checks = []

    def delayed_ready(path):
        readiness_checks.append(path)
        return len(readiness_checks) > 2 and real_ready(path)

    monkeypatch.setattr("publish_scores.publication_ready", delayed_ready)
    monkeypatch.setattr("publish_scores.time.sleep", lambda _: None)
    assert publish(run, "musescore3", "node", tmp_path / "unused.js", "pdfinfo",
                   force=False, render_workers=2) == result
    assert len(readiness_checks) == 3


def test_publication_exports_both_guitars_when_second_is_generated(tmp_path, monkeypatch):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fixture")
    args = SimpleNamespace(audio=audio, output_dir=tmp_path / "run", original="guitar1",
                           requested="guitar2", model="model", midigpt_model="yellow_medium",
                           device="cpu", beat_checkpoint="checkpoint", seed=0, resume=False,
                           modules_root=tmp_path, model_python=Path(sys.executable),
                           tab_python=Path(sys.executable), musescore="musescore3", node="node",
                           gp5_converter=tmp_path / "convert.js", pdfinfo="pdfinfo",
                           bsroformer_models_dir=tmp_path / "models", bsroformer_lib_dir=tmp_path / "pylib")
    args.gp5_converter.write_text("// stub", encoding="utf-8")
    runner = Runner(args)
    score = pretty_midi.PrettyMIDI()
    score.instruments = [instrument(26, "Guitar 1"), instrument(29, "Guitar 2 (AI generated)")]
    score.write(str(runner.out / "full_score.mid"))
    for directory in ("guitar", "guitar_generated"):
        path = runner.out / directory
        path.mkdir()
        (path / "guitar.gp5").write_bytes(b"GP5 fixture")
    runner.manifest.update(status="complete", completed=["assemble"],
                           guitar_score_dir="guitar", guitar_extra_dir="guitar_generated")
    runner.manifest_path.write_text(json.dumps(runner.manifest), encoding="utf-8")
    calls = []

    def fake_converter(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "pdfinfo":
            return subprocess.CompletedProcess(cmd, 0, stdout="Pages: 1\n")
        fake_score_export(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("publish_scores.subprocess.run", fake_converter)
    monkeypatch.setattr("publish_scores.shutil.which", lambda executable: executable)
    monkeypatch.setattr("publish_scores.gp5_score", fake_gp5_score)
    runner.publish_outputs()
    contract = json.loads((runner.out / "scores" / "score_outputs.json").read_text(encoding="utf-8"))
    assert contract["version"] == 4
    assert set(contract["instruments"]) == {"guitar", "guitar_1", "guitar_2"}
    assert contract["instruments"]["guitar"]["converter"] == "musescore-score"
    assert contract["instruments"]["guitar_1"]["converter"] == "gp5-to-pdf"
    assert contract["instruments"]["guitar_2"]["source"] == "scores/guitar_2_render.gp5"
    assert len(pretty_midi.PrettyMIDI(str(runner.out / "scores" / "guitar_2.mid")).instruments) == 1
    assert {Path(cmd[3]).name for cmd in calls if cmd[0] == "node"} == {"guitar_1.pdf", "guitar_2.pdf"}
    assert publication_ready(runner.out)
