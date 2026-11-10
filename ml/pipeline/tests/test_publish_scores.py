"""Output-contract checks that do not require a browser or notation renderer."""

import copy
import json
from pathlib import Path
import sys

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_scores
from publish_scores import (choose_gp5, export_part_midi, family, gp5_score, notation_midi,
                            skyline_track_order)


def test_keyboard_pdf_keeps_three_muscriptor_tracks(tmp_path):
    score = pretty_midi.PrettyMIDI(initial_tempo=162)
    for name, program in (("piano: acoustic piano", 0),
                          ("piano: electric piano", 2), ("piano: organ", 16),
                          ("drums: drums", 0)):
        track = pretty_midi.Instrument(program=program, is_drum=name.startswith("drums:"), name=name)
        track.notes.append(pretty_midi.Note(90, 60 if not track.is_drum else 38, 0, 1))
        score.instruments.append(track)
    output = tmp_path / "piano.mid"
    tracks = export_part_midi(score, "piano", output)
    loaded = pretty_midi.PrettyMIDI(str(output))
    assert [track["program"] for track in tracks] == [0, 2, 16]
    assert len(loaded.instruments) == 3
    assert all(family(track) == "piano" for track in loaded.instruments)
    assert loaded.get_tempo_changes()[1][0] == pytest.approx(162, abs=0.001)


def test_gp5_source_must_be_unambiguous(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        choose_gp5(tmp_path, "guitar")
    (tmp_path / "a.gp5").write_bytes(b"a")
    assert choose_gp5(tmp_path, "guitar").name == "a.gp5"
    (tmp_path / "b.gp5").write_bytes(b"b")
    with pytest.raises(ValueError, match="exactly one"):
        choose_gp5(tmp_path, "guitar")


def test_drum_notation_copy_preserves_original(tmp_path):
    score = pretty_midi.PrettyMIDI()
    track = pretty_midi.Instrument(program=0, is_drum=True, name="drums: drums")
    for pitch in (39, 70, 82, 38):
        track.notes.append(pretty_midi.Note(100, pitch, pitch / 100, pitch / 100 + 0.1))
    score.instruments.append(track)
    output = tmp_path / "notation.mid"
    assert notation_midi(score, output) == {39: 1, 70: 1, 82: 1}
    assert [n.pitch for n in score.instruments[0].notes] == [39, 70, 82, 38]
    assert sorted(n.pitch for n in pretty_midi.PrettyMIDI(str(output)).instruments[0].notes) == [38, 38, 44, 54]


def two_track_gp5(path):
    guitarpro = pytest.importorskip("guitarpro")
    song = guitarpro.models.Song()
    song.tracks[0].name = "Guitar 1 (lead)"
    second = copy.deepcopy(song.tracks[0])
    second.number, second.name = 2, "Guitar 2 (rhythm)"
    for measure in second.measures:
        measure.track = second
    song.tracks.append(second)
    guitarpro.write(song, str(path))


def test_skyline_gp5_track_can_be_published_alone(tmp_path):
    guitarpro = pytest.importorskip("guitarpro")
    source = tmp_path / "skyline lead+rhythm.gp5"
    two_track_gp5(source)
    target = tmp_path / "guitar_2_render.gp5"
    gp5_score(source, target, [("Electric Guitar 2", 29)], keep_track=1)
    song = guitarpro.parse(str(target))
    assert [track.name for track in song.tracks] == ["Electric Guitar 2"]
    assert song.tracks[0].number == 1 and song.tracks[0].channel.instrument == 29
    with pytest.raises(ValueError, match="no track 3"):
        gp5_score(source, tmp_path / "bad.gp5", [("x", 29)], keep_track=2)


def fake_tools(command, check):
    """Stand in for MuseScore and the alphaTab converter: write each -o target."""
    if command[0] == "node":
        source, target = Path(command[2]), Path(command[3])
    else:
        target, source = Path(command[2]), Path(command[3])
    if target.suffix == ".mscx":
        tracks = [t for t in pretty_midi.PrettyMIDI(str(source)).instruments if t.notes]
        parts = "".join("<Part><Instrument/></Part>" for _ in tracks)
        target.write_text(f"<museScore><Score>{parts}</Score></museScore>")
    elif target.suffix == ".mp3":
        target.write_bytes(b"ID3" + b"\0" * 2000)
    else:
        target.write_bytes(b"%PDF" + source.read_bytes()[:64] + b"\0" * 2000)


def test_two_skyline_guitars_get_separate_pdfs(tmp_path, monkeypatch):
    pytest.importorskip("guitarpro")
    run = tmp_path / "run"
    (run / "guitar").mkdir(parents=True)
    score = pretty_midi.PrettyMIDI()
    for name, program in (("Guitar 1 (lead)", 29), ("Guitar 2 (rhythm)", 29)):
        track = pretty_midi.Instrument(program=program, name=name)
        track.notes.append(pretty_midi.Note(90, 64, 0, 1))
        score.instruments.append(track)
    score.write(str(run / "full_score.mid"))
    two_track_gp5(run / "guitar" / "skyline lead+rhythm.gp5")
    (run / "manifest.json").write_text(json.dumps({"status": "complete", "guitar_score_dir": "guitar"}))
    monkeypatch.setattr(publish_scores.subprocess, "run", fake_tools)
    monkeypatch.setattr(publish_scores.shutil, "which", lambda name: name)
    monkeypatch.setattr(publish_scores, "pdf_pages", lambda path, pdfinfo: 1)
    converter = tmp_path / "convert.js"
    converter.write_text("")

    contract = publish_scores.publish(run, "musescore3", "node", converter, "pdfinfo", False)

    assert set(contract["instruments"]) == {"guitar", "guitar_1", "guitar_2"}
    assert set(contract["audio"]["instruments"]) == {"guitar", "guitar_1", "guitar_2"}
    assert contract["instruments"]["guitar_2"]["pdf"] == "scores/guitar_2.pdf"
    names = [track.name for track in
             __import__("guitarpro").parse(str(run / "scores" / "guitar_2_render.gp5")).tracks]
    assert names == ["Electric Guitar 2"]
    assert publish_scores.publication_ready(run)


def test_skyline_tracks_are_paired_by_lead_rhythm_name():
    gp5 = ["Guitar 1 (lead)", "Guitar 2 (rhythm)"]
    assert skyline_track_order(gp5, ["Guitar 1 (lead)", "Guitar 2 (rhythm)"]) == [0, 1]
    # if the assembled score lists rhythm first, guitar_1 must take the rhythm TAB
    assert skyline_track_order(gp5, ["AI generated guitar: Guitar 2 (rhythm)", "Guitar 1 (lead)"]) == [1, 0]
    # without skyline names the tracks stay paired by position
    assert skyline_track_order(gp5, ["Guitar", "Guitar"]) == [0, 1]
    assert skyline_track_order(["Track 1", "Track 2"], ["Guitar 2 (rhythm)", "Guitar 1 (lead)"]) == [0, 1]


def test_swapped_score_guitars_get_matching_gp5_tracks(tmp_path, monkeypatch):
    guitarpro = pytest.importorskip("guitarpro")
    run = tmp_path / "run"
    (run / "guitar").mkdir(parents=True)
    score = pretty_midi.PrettyMIDI()
    for name in ("Guitar 2 (rhythm)", "Guitar 1 (lead)"):
        track = pretty_midi.Instrument(program=29, name=name)
        track.notes.append(pretty_midi.Note(90, 64, 0, 1))
        score.instruments.append(track)
    score.write(str(run / "full_score.mid"))
    source = run / "guitar" / "skyline lead+rhythm.gp5"
    two_track_gp5(source)
    song = guitarpro.parse(str(source))
    song.tracks[1].strings[0].value = 62  # mark the rhythm track
    guitarpro.write(song, str(source))
    (run / "manifest.json").write_text(json.dumps({"status": "complete", "guitar_score_dir": "guitar"}))
    monkeypatch.setattr(publish_scores.subprocess, "run", fake_tools)
    monkeypatch.setattr(publish_scores.shutil, "which", lambda name: name)
    monkeypatch.setattr(publish_scores, "pdf_pages", lambda path, pdfinfo: 1)
    converter = tmp_path / "convert.js"
    converter.write_text("")

    publish_scores.publish(run, "musescore3", "node", converter, "pdfinfo", False)

    first = guitarpro.parse(str(run / "scores" / "guitar_1_render.gp5")).tracks[0]
    second = guitarpro.parse(str(run / "scores" / "guitar_2_render.gp5")).tracks[0]
    assert first.strings[0].value == 62 and second.strings[0].value != 62
