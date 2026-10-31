"""Output-contract checks that do not require a browser or notation renderer."""

from pathlib import Path
import sys

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publish_scores import choose_gp5, export_part_midi, family, notation_midi


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
