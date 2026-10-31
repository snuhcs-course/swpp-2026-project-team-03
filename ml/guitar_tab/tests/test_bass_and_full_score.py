"""bass_tab.py and full_score.py unit tests. tuttut is not needed.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import sys
from pathlib import Path

import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bass_tab import BASS_TUNINGS, bass_line, bass_notes  # noqa: E402
from full_score import build, guitar_tracks  # noqa: E402
from skyline_tab import TUNINGS  # noqa: E402


def N(pitch, start, end):
    return pretty_midi.Note(velocity=100, pitch=pitch, start=start, end=end)


def inst(program, notes, name="", drum=False):
    i = pretty_midi.Instrument(program=program, name=name, is_drum=drum)
    i.notes = list(notes)
    return i


# ----------------------------------------------------------------------
# bass_tab
# ----------------------------------------------------------------------
def test_bass_tunings_are_registered_for_tuttut():
    for k, v in BASS_TUNINGS.items():
        assert TUNINGS[k] == v


def test_only_bass_programs_are_used():
    pm = pretty_midi.PrettyMIDI()
    pm.instruments += [inst(33, [N(40, 0, 1)]), inst(29, [N(60, 0, 1)]), inst(0, [N(36, 0, 1)], drum=True)]
    assert [n.pitch for n in bass_notes(pm)] == [40]


def test_lowest_note_per_onset_is_kept():
    out, st = bass_line([N(45, 0.0, 1.0), N(40, 0.0, 0.5), N(52, 0.0, 1.0), N(43, 1.0, 2.0)], "bass_standard")
    assert [(n.pitch, n.start, n.end) for n in out] == [(40, 0.0, 0.5), (43, 1.0, 2.0)]
    assert st == {"notes_in": 4, "chord_notes_dropped": 2, "octave_folded": 0}


def test_notes_below_the_low_string_move_up_an_octave():
    out, st = bass_line([N(26, 0.0, 1.0)], "bass_standard")          # D1 < E1 (28)
    assert out[0].pitch == 38 and st["octave_folded"] == 1
    out, st = bass_line([N(26, 0.0, 1.0)], "bass_drop_d")            # D1 is the open low string
    assert out[0].pitch == 26 and st["octave_folded"] == 0


def test_empty_bass():
    assert bass_line([], "bass_standard") == ([], {"notes_in": 0, "chord_notes_dropped": 0, "octave_folded": 0})


# ----------------------------------------------------------------------
# full_score
# ----------------------------------------------------------------------
def _aligned():
    pm = pretty_midi.PrettyMIDI(initial_tempo=150, resolution=480)
    pm.time_signature_changes = [pretty_midi.TimeSignature(12, 8, 0.0)]
    pm.instruments += [inst(0, [N(36, 0, 0.1)], "drums", drum=True), inst(33, [N(40, 0, 1)], "raw bass"),
                       inst(26, [N(60, 0, 1)], "raw guitar 1"), inst(29, [N(64, 0, 1)], "raw guitar 2"),
                       inst(0, [N(72, 0, 1)], "piano")]
    return pm


def test_full_score_replaces_guitar_and_bass_and_keeps_the_rest():
    guitars = [inst(29, [N(64, 0, 1)], "Guitar 1 (lead)"), inst(29, [N(52, 0, 1)], "Guitar 2 (rhythm)")]
    out = build(_aligned(), guitars, [inst(33, [N(28, 0, 1)], "Bass")])
    assert [i.name for i in out.instruments] == ["Guitar 1 (lead)", "Guitar 2 (rhythm)", "Bass (TAB processed)", "piano", "drums"]
    assert [i.program for i in out.instruments[:2]] == [26, 26]      # sound of the first aligned guitar
    assert out.instruments[2].notes[0].pitch == 28 and out.instruments[-1].is_drum
    ts = out.time_signature_changes[0]
    assert (ts.numerator, ts.denominator) == (12, 8) and out.resolution == 480
    assert round(out.get_tempo_changes()[1][0]) == 150


def test_full_score_without_bass_drops_the_raw_bass():
    out = build(_aligned(), [inst(29, [N(64, 0, 1)], "Guitar")], [])
    assert [i.name for i in out.instruments] == ["Guitar", "piano", "drums"]


def test_guitar_tracks_prefers_the_split_file(tmp_path):
    for name, n in (("skyline_lead_rhythm.mid", 2), ("guitar.mid", 1)):
        pm = pretty_midi.PrettyMIDI()
        pm.instruments += [inst(29, [N(60, 0, 1)], f"{name}{k}") for k in range(n)]
        pm.write(str(tmp_path / name))
    assert len(guitar_tracks(tmp_path)) == 2
    (tmp_path / "skyline_lead_rhythm.mid").unlink()
    assert len(guitar_tracks(tmp_path)) == 1
