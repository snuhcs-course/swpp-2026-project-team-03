"""skyline_tab.py unit tests. tuttut is not needed: TAB objects are stubbed.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import sys
from pathlib import Path

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skyline_tab import (TUNINGS, choose_tuning, decide_split, fold_range, guitar_notes, playable,  # noqa: E402
                         reduce_chord, reduce_chords, split_and_clean, split_len, track_events, write_gp5)

gp = pytest.importorskip("guitarpro")


def N(pitch, start, end):
    return pretty_midi.Note(velocity=100, pitch=pitch, start=start, end=end)


# ----------------------------------------------------------------------
# tuning and range
# ----------------------------------------------------------------------
def test_standard_tuning_when_notes_fit():
    assert choose_tuning([40, 45, 52, 64] * 50) == "standard"


def test_half_step_down_when_low_e_flat_is_common():
    assert choose_tuning([39] * 5 + [50] * 95) == "half_step_down"


def test_drop_d_when_low_d_is_common():
    assert choose_tuning([38] * 5 + [50] * 95) == "drop_d"


def test_fold_range_moves_by_octaves():
    assert fold_range(28, "standard") == 40          # E1 -> E2
    assert fold_range(100, "standard") == 76         # above fret 20 of the high E
    assert fold_range(60, "standard") == 60


# ----------------------------------------------------------------------
# playable chords
# ----------------------------------------------------------------------
def test_open_e_major_is_playable():
    assert playable([40, 47, 52, 56, 59, 64], "standard")


def test_open_string_does_not_count_toward_the_span():
    assert playable([40, 84], "standard")             # open low E + fret 20 on the high E


def test_two_notes_too_far_apart_are_reduced_to_the_lower():
    assert reduce_chord([41, 84], "standard") == [41]  # fret 1 and fret 20: no shape fits


def test_seven_notes_become_at_most_six_playable_notes():
    kept = reduce_chord([40, 45, 50, 55, 59, 64, 67], "standard")
    assert len(kept) <= 6 and playable(kept, "standard")
    assert kept[0] == 40 and kept[-1] == 67           # lowest and highest are kept


def test_merged_chords_are_reduced_to_playable_shapes():
    notes = [N(p, 0.0, 1.0) for p in (40, 45, 50, 55, 59, 64, 67)] + [N(41, 1.0, 2.0), N(84, 1.0, 2.0)]
    out, st = reduce_chords(notes, "standard")
    first = sorted(n.pitch for n in out if n.start == 0.0)
    second = [n.pitch for n in out if n.start == 1.0]
    assert len(first) <= 6 and playable(first, "standard")
    assert second == [41]
    assert st["notes_in"] == 9 and st["notes_dropped"] == 9 - len(out)


def test_merged_same_pitch_at_same_onset_becomes_one_note():
    out, st = reduce_chords([N(52, 0.0, 0.5), N(52, 0.0, 1.5), N(28, 0.0, 1.0)], "standard")
    assert sorted((n.pitch, n.end) for n in out) == [(40, 1.0), (52, 1.5)]   # 28 folds to 40
    assert st["notes_in"] == 2


def test_merged_single_notes_are_kept():
    out, st = reduce_chords([N(60, 0.0, 1.0), N(62, 1.0, 2.0)], "standard")
    assert [n.pitch for n in out] == [60, 62] and st["notes_dropped"] == 0


def test_rhythm_chords_are_kept_without_chord_reduction():
    notes = [N(41, 0.0, 1.0), N(84, 0.0, 1.0), N(86, 0.0, 1.0)]
    _, rhythm, st = split_and_clean(notes, "standard", chord_reduction=False)
    assert sorted(n.pitch for n in rhythm) == [41, 84] and st["rhythm_notes_dropped"] == 0
    _, rhythm, _ = split_and_clean(notes, "standard")
    assert [n.pitch for n in rhythm] == [41]


# ----------------------------------------------------------------------
# skyline split
# ----------------------------------------------------------------------
def test_highest_note_goes_to_lead_rest_to_rhythm():
    notes = [N(40, 0.0, 1.0), N(47, 0.0, 1.0), N(64, 0.0, 0.5), N(66, 0.5, 1.0)]
    lead, rhythm, st = split_and_clean(notes, "standard")
    assert [n.pitch for n in lead] == [64, 66]
    assert sorted(n.pitch for n in rhythm) == [40, 47]
    assert st["lead_notes"] == 2 and st["rhythm_notes"] == 2


def test_lead_is_monophonic():
    notes = [N(64, 0.0, 2.0), N(67, 0.5, 1.0)]
    lead, _, _ = split_and_clean(notes, "standard")
    assert lead[0].end == pytest.approx(0.5)


def test_only_guitar_programs_are_used():
    pm = pretty_midi.PrettyMIDI()
    g = pretty_midi.Instrument(program=29)
    g.notes = [N(60, 0, 1)]
    b = pretty_midi.Instrument(program=33)
    b.notes = [N(40, 0, 1)]
    pm.instruments += [g, b]
    assert [n.pitch for n in guitar_notes(pm)] == [60]


# ----------------------------------------------------------------------
# Guitar Pro export
# ----------------------------------------------------------------------
@pytest.mark.parametrize("n", range(1, 33))
def test_split_len_sums_to_input(n):
    assert sum(L for L, _, _ in split_len(n)) == n


class _StubTab:
    """Minimal stand-in for tuttut.logic.tab.Tab (tab dict + midi)."""

    def __init__(self, events):
        self.midi = pretty_midi.PrettyMIDI(initial_tempo=120, resolution=480)
        self.tab = {"measures": [{"events": events}]}


def test_track_events_lengths_come_from_notes_and_next_onset():
    # 120 BPM: 16th = 0.125 s = 120 ticks
    tab = _StubTab([
        {"time": 0.0, "time_ticks": 0, "notes": [{"string": 0, "fret": 3}]},
        {"time": 0.25, "time_ticks": 240, "notes": [{"string": 1, "fret": 5}]},
    ])
    notes = [N(67, 0.0, 1.0), N(64, 0.25, 0.5)]
    ev = track_events(tab, notes, 120)
    assert ev == [(0, 2, [(1, 3)]), (2, 2, [(2, 5)])]


def test_gp5_roundtrip_keeps_frets_and_bar_lengths(tmp_path):
    lead = [(0, 4, [(1, 3)]), (4, 16, [(2, 5)])]          # second note crosses the barline
    rhythm = [(0, 8, [(5, 3), (4, 2)])]
    path = tmp_path / "t.gp5"
    n = write_gp5(path, "흰수염고래 - YB", 120, 4, "half_step_down",
                  [("lead", lead), ("rhythm", rhythm)])
    song = gp.parse(str(path))
    assert n == 2 and len(song.tracks) == 2
    assert song.title.startswith("Huinsuyeom Gorae")
    assert [s.value for s in song.tracks[0].strings] == TUNINGS["half_step_down"]
    for track in song.tracks:
        for m in track.measures:
            total = sum({1: 16, 2: 8, 4: 4, 8: 2, 16: 1}[b.duration.value] * (1.5 if b.duration.isDotted else 1)
                        for b in m.voices[0].beats)
            assert total == 16
    first = song.tracks[0].measures[0].voices[0].beats
    assert (first[0].notes[0].string, first[0].notes[0].value) == (1, 3)
    tied = song.tracks[0].measures[1].voices[0].beats[0].notes[0]
    assert tied.type == gp.NoteType.tie and tied.value == 5


def test_gp5_twelve_eight_bars_are_24_sixteenths(tmp_path):
    path = tmp_path / "c.gp5"
    n = write_gp5(path, "12-8 song", 162, 12, "standard", [("g", [(0, 6, [(1, 0)]), (20, 8, [(2, 1)])])], denominator=8)
    song = gp.parse(str(path))
    sig = song.measureHeaders[0].timeSignature
    assert (sig.numerator, sig.denominator.value) == (12, 8) and n == 2
    for m in song.tracks[0].measures:
        total = sum({1: 16, 2: 8, 4: 4, 8: 2, 16: 1}[b.duration.value] * (1.5 if b.duration.isDotted else 1)
                    for b in m.voices[0].beats)
        assert total == 24


# ----------------------------------------------------------------------
# auto split: two guitars or one?
# ----------------------------------------------------------------------
def _onsets(chords, step=0.5):
    return [N(p, k * step, k * step + 0.4) for k, ps in enumerate(chords) for p in ps]


def test_two_guitars_in_two_registers_are_split():
    # low rhythm power chord + high lead note, three octaves apart, every onset: unplayable and wide
    split, st = decide_split(_onsets([[40, 47, 52, 84]] * 20), "standard")
    assert split and st["unplayable"] == 1.0 and st["wide"] == 1.0


def test_one_guitar_with_extra_notes_is_not_split():
    # cramped cluster: unplayable as one chord, but within two octaves -> chord reduction, not a second guitar
    split, st = decide_split(_onsets([[52, 53, 54, 55, 56, 57, 58]] * 20), "standard")
    assert not split and st["unplayable"] == 1.0 and st["wide"] == 0.0


def test_playable_chords_are_not_split():
    split, st = decide_split(_onsets([[40, 47, 52, 56, 59, 64]] * 20), "standard")   # open E major
    assert not split and st["unplayable"] == 0.0


def test_wide_but_playable_is_not_split():
    # open low E + fret 20 on the high E: wider than two octaves but one guitar can play it
    split, st = decide_split(_onsets([[40, 84]] * 20), "standard")
    assert not split and st["wide"] == 1.0 and st["unplayable"] == 0.0


def test_split_thresholds_are_shares_of_onsets():
    chords = [[40, 47, 52, 84]] * 2 + [[60]] * 18          # 10% unplayable and wide
    assert decide_split(_onsets(chords), "standard")[0]
    chords = [[40, 47, 52, 84]] * 1 + [[60]] * 19          # 5% unplayable, 5% wide -> wide below 6%
    assert not decide_split(_onsets(chords), "standard")[0]


def test_empty_part():
    assert decide_split([], "standard") == (False, {"onsets": 0, "unplayable": 0.0, "wide": 0.0})


# ----------------------------------------------------------------------
# jump count from text TAB
# ----------------------------------------------------------------------
def test_jump_stats_counts_moves_over_five_frets(tmp_path):
    from skyline_tab import jump_stats
    p = tmp_path / "t.txt"
    p.write_text("E ||--2--14--13--0--|\n"
                 "B ||----------------|\n")
    n, big, med = jump_stats(p)
    assert n == 3            # open string (0) events are not positions
    assert big == 1          # 2 -> 14
    assert med == pytest.approx(6.5)
