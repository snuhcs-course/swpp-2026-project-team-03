"""bass_tab.py end to end: main() and the command line on a small MIDI, files written to a temporary folder.

Needs tuttut (fingering) and guitarpro (GP5); skipped where they are not installed.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import sys
from pathlib import Path

import pretty_midi
import pytest

pytest.importorskip("tuttut")
gp = pytest.importorskip("guitarpro")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bass_tab  # noqa: E402


def _song(path, bass_pitches, guitar_pitches=(), ts=(4, 4)):
    """Aligned-style MIDI: 120 BPM, one note per 8th, a bass track (+ optional guitar)."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=120, resolution=480)
    pm.time_signature_changes = [pretty_midi.TimeSignature(ts[0], ts[1], 0.0)]
    bass = pretty_midi.Instrument(33, name="bass")
    for k, p in enumerate(bass_pitches):
        bass.notes.append(pretty_midi.Note(100, p, k * 0.25, k * 0.25 + 0.2))
    bass.notes.append(pretty_midi.Note(100, bass_pitches[0] + 7, 0.0, 0.2))   # chord note at the first onset
    pm.instruments.append(bass)
    if guitar_pitches:
        gtr = pretty_midi.Instrument(29, name="guitar")
        gtr.notes = [pretty_midi.Note(100, p, k * 0.5, k * 0.5 + 0.4) for k, p in enumerate(guitar_pitches)]
        pm.instruments.append(gtr)
    pm.write(str(path))
    return path


def test_main_writes_midi_tab_and_gp5(tmp_path):
    src = _song(tmp_path / "song_aligned.mid", [28, 33, 38, 43, 40, 36, 31, 28] * 4, [52, 55, 59, 64] * 8)
    out = tmp_path / "out"
    stats = bass_tab.main(str(src), out)
    assert stats == {"notes_in": 33, "chord_notes_dropped": 1, "octave_folded": 0}
    assert (out / "bass.mid").exists() and (out / "tab_bass.txt").exists()
    mid = pretty_midi.PrettyMIDI(str(out / "bass.mid"))
    assert [i.program for i in mid.instruments] == [bass_tab.BASS_PROGRAM]
    assert len(mid.instruments[0].notes) == 32
    song = gp.parse(str(out / "song - bass.gp5"))                 # "_aligned" is dropped from the title
    assert song.tracks[0].channel.instrument == bass_tab.BASS_PROGRAM
    assert len(song.tracks[0].strings) == 4


def test_main_without_bass_notes_writes_nothing(tmp_path):
    pm = pretty_midi.PrettyMIDI()
    pm.instruments.append(pretty_midi.Instrument(29, name="guitar"))
    pm.write(str(tmp_path / "empty.mid"))
    stats = bass_tab.main(str(tmp_path / "empty.mid"), tmp_path / "out")
    assert stats["notes_in"] == 0 and not (tmp_path / "out" / "bass.mid").exists()


def test_cli_fixed_tuning_folds_low_notes(tmp_path, capsys):
    src = _song(tmp_path / "low.mid", [26, 33, 38, 26] * 4, ts=(6, 8))      # D1 is below a standard bass
    bass_tab.cli([str(src), str(tmp_path / "out"), "--tuning", "bass_standard"])
    assert "octave-folded 8" in capsys.readouterr().out
    pitches = {n.pitch for n in pretty_midi.PrettyMIDI(str(tmp_path / "out" / "bass.mid")).instruments[0].notes}
    assert pitches == {33, 38}                                             # D1 (26) -> D2 (38); A1 stays
