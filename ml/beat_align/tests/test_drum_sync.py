"""drum_sync.py 단위 테스트.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drum_sync import MAX_CORRECTION, drum_sync, grid_error, local_lag, main  # noqa: E402


def song(drum_times, guitar_times, guitar_len=0.2):
    pm = pretty_midi.PrettyMIDI()
    d = pretty_midi.Instrument(program=0, is_drum=True)
    d.notes = [pretty_midi.Note(100, 38, t, t + 0.1) for t in drum_times]
    g = pretty_midi.Instrument(program=29)
    g.notes = [pretty_midi.Note(100, 60, t, t + guitar_len) for t in guitar_times]
    pm.instruments += [d, g]
    return pm


def test_late_guitar_is_pulled_back_to_drums():
    drums = np.arange(0, 20) * 0.5
    pm = song(drums, drums + 0.06)                       # 기타가 60 ms 늦음
    r = drum_sync(pm)
    starts = np.array([n.start for n in pm.instruments[1].notes])
    assert np.allclose(starts, drums, atol=1e-6)
    assert r.moved_notes == 20 and r.max_shift == pytest.approx(0.06)
    lengths = [n.end - n.start for n in pm.instruments[1].notes]
    assert np.allclose(lengths, 0.2)                      # 길이는 그대로


def test_drums_are_not_moved():
    drums = np.arange(0, 10) * 0.5
    pm = song(drums, drums + 0.05)
    drum_sync(pm)
    assert np.allclose([n.start for n in pm.instruments[0].notes], drums)


def test_lag_follows_local_drift():
    # 0~5 s는 늦지 않고, 10~15 s는 80 ms 늦음 → 구간마다 다르게 보정
    drums = np.arange(0, 30) * 0.5
    guitar = np.where(drums >= 10, drums + 0.08, drums)
    lag = local_lag(guitar, drums)
    assert np.allclose(lag[drums < 8], 0.0) and np.allclose(lag[drums >= 12], 0.08)


def test_correction_is_capped():
    drums = np.arange(0, 10) * 1.0
    lag = local_lag(drums + 0.105, drums)                # 110 ms 안이라 같이 친 음으로 봄, 보정은 100 ms까지만
    assert np.allclose(lag, MAX_CORRECTION)


def test_needs_enough_matches():
    drums = np.array([0.0, 0.5])
    assert np.allclose(local_lag([0.05, 0.55], drums), 0.0)   # 같이 친 음이 2개뿐


def test_far_notes_are_not_evidence():
    drums = np.arange(0, 10) * 0.5
    off = drums + 0.25                                   # 박 사이(엇박) 음: 드럼과 같이 친 음이 아님
    assert np.allclose(local_lag(off, drums), 0.0)


def test_no_drums_changes_nothing():
    pm = pretty_midi.PrettyMIDI()
    g = pretty_midi.Instrument(program=29)
    g.notes = [pretty_midi.Note(100, 60, 1.0, 1.2)]
    pm.instruments.append(g)
    r = drum_sync(pm)
    assert pm.instruments[0].notes[0].start == 1.0 and r.drum_notes == 0 and r.moved_notes == 0
    assert np.allclose(local_lag([], [1.0]), [])


def test_cli(tmp_path, capsys):
    drums = np.arange(0, 20) * 0.5
    song(drums, drums + 0.06).write(str(tmp_path / "in.mid"))
    assert main([str(tmp_path / "in.mid"), str(tmp_path / "out.mid")]) == 0
    assert "moved 20 notes" in capsys.readouterr().out
    out = pretty_midi.PrettyMIDI(str(tmp_path / "out.mid"))
    assert np.allclose([n.start for n in out.instruments[1].notes], drums, atol=0.002)


# ----------------------------------------------------------------------
# grid guard (2026-11 interview: 간주 엇박 연결이 정박으로 들어감)
# ----------------------------------------------------------------------
def _band(bpm, offset16, drift=0.0, n_beats=48):
    """kick/snare on every beat, hi-hat on the 8ths; bass every 2 beats at offset16 16ths from the beat."""
    b = 60 / bpm
    s16 = b / 4
    pm = pretty_midi.PrettyMIDI()
    d = pretty_midi.Instrument(0, is_drum=True)
    bass = pretty_midi.Instrument(33)
    for k in range(n_beats):
        d.notes.append(pretty_midi.Note(100, 36 if k % 2 == 0 else 38, k * b, k * b + 0.05))
        d.notes.append(pretty_midi.Note(80, 42, k * b + b / 2, k * b + b / 2 + 0.05))
    for k in range(2, n_beats, 2):
        t = k * b + offset16 * s16 + drift
        bass.notes.append(pretty_midi.Note(100, 40, t, t + s16))
    pm.instruments += [d, bass]
    return pm, [k * b for k in range(n_beats)]


def test_fast_syncopation_is_pulled_onto_the_beat_without_beats():
    # 172 BPM: a 16th (87 ms) is inside MATCH_TOLERANCE, so the old rule reads the anticipation as lag
    pm, _ = _band(172, -1)
    r = drum_sync(pm)
    assert r.moved_notes > len(pm.instruments[1].notes) // 2


def test_grid_guard_keeps_fast_syncopation():
    pm, beats = _band(172, -1)
    before = [n.start for n in pm.instruments[1].notes]
    r = drum_sync(pm, beats=beats)
    after = [n.start for n in pm.instruments[1].notes]
    assert r.grid_kept > 0
    assert sum(abs(a - b) > 0.02 for a, b in zip(after, before)) <= 1


def test_grid_guard_still_fixes_muscriptor_lag():
    # 125 BPM, every bass note 80 ms late (off the 16th grid): still corrected
    pm, beats = _band(125, 0, drift=0.08)
    r = drum_sync(pm, beats=beats)
    assert r.moved_notes == len(pm.instruments[1].notes)
    assert all(abs(n.start - round(n.start / (60 / 125 / 4)) * (60 / 125 / 4)) < 0.01 for n in pm.instruments[1].notes)


def test_grid_error_counts_triplet_cells_as_on_grid():
    beats = [0.0, 0.5, 1.0, 1.5]
    assert grid_error([0.5 + 0.5 / 3], beats)[0] < 1e-9     # triplet 8th
    assert grid_error([0.5 + 0.125], beats)[0] < 1e-9       # 16th
    assert grid_error([0.5 + 0.0625], beats)[0] > 0.05      # 32nd: off grid
