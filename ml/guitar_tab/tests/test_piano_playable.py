"""piano_playable.py unit tests.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import sys
from pathlib import Path

import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from full_score import build  # noqa: E402
from piano_playable import hand_limit, merge_reattacks, playable, process  # noqa: E402

S16 = 0.125   # 120 BPM


def N(pitch, k, length=1, vel=100):
    """note at 16th index k, `length` 16ths long"""
    return pretty_midi.Note(velocity=vel, pitch=pitch, start=k * S16, end=(k + length) * S16)


def test_sixteenth_reattacks_become_one_held_note():
    out, merged = merge_reattacks([N(60, k) for k in range(8)], S16)
    assert merged == 7 and len(out) == 1
    assert (out[0].start, out[0].end) == (0.0, 8 * S16)


def test_one_missing_sixteenth_still_merges():
    ks = [0, 1, 2, 3, 5, 6, 7, 8]                              # mostly 1/16 apart
    out, merged = merge_reattacks([N(60, k) for k in ks], S16)
    assert len(out) == 1 and merged == 7


def test_repeated_eighths_and_short_runs_stay():
    eighths = [N(60, 2 * k) for k in range(8)]
    assert merge_reattacks(eighths, S16) == (eighths, 0)
    short = [N(62, k) for k in range(5)]                       # below MERGE_MIN_RUN
    assert merge_reattacks(short, S16)[1] == 0


def test_hand_limit_keeps_playable_chords():
    assert hand_limit([48, 52, 55, 60, 64, 67]) == [48, 52, 55, 60, 64, 67]   # C3-G4, two hands
    assert hand_limit([60, 64, 67]) == [60, 64, 67]                           # one hand


def test_hand_limit_drops_the_middle_of_a_three_octave_chord():
    chord = [64, 68, 71, 76, 80, 83, 88, 92, 95]               # E4 ... B6
    kept = hand_limit(chord)
    assert kept == [64, 68, 71, 76, 83, 88, 92, 95]            # G#5 (80) is in neither hand
    left, right = [p for p in kept if p <= 64 + 14], [p for p in kept if p >= 95 - 14]
    assert len(left) <= 5 and len(right) <= 5


def test_each_hand_keeps_its_outer_note_and_drops_octave_doublings_first():
    right = [72, 74, 76, 79, 81, 84, 86]                       # 7 notes within an octave+2 of the top
    kept = hand_limit(right)
    assert len(kept) == 5 and 86 in kept and 74 not in kept     # D5 doubles the top D6


def test_tracks_count_as_one_player():
    piano = [N(60, 0), N(64, 0)]
    organ = [N(60, 0, vel=50), N(67, 0)]                       # C4 struck in both tracks
    out, st = playable([piano, organ], S16)
    assert sorted(n.pitch for n in out[0]) == [60, 64] and [n.pitch for n in out[1]] == [67]
    assert st == {"reattacks_merged": 0, "same_pitch_doubles": 1, "hand_limit_dropped": 0}


def _song():
    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    keys = pretty_midi.Instrument(16, name="piano: organ")
    keys.notes = [N(p, k) for k in range(8) for p in (64, 68, 71, 76, 80, 83, 88, 92, 95)]
    gtr = pretty_midi.Instrument(29, name="guitar")
    gtr.notes = [N(p, 0) for p in (40, 47, 52, 56, 59, 64, 68)]
    pm.instruments += [keys, gtr]
    return pm


def test_process_touches_only_keyboard_tracks():
    out, st = process(_song())
    keys, gtr = out.instruments
    assert len(keys.notes) == 8 and all(n.end == 8 * S16 for n in keys.notes)   # one held chord
    assert len(gtr.notes) == 7
    assert st["reattacks_merged"] == 63 and st["hand_limit_dropped"] == 1


def test_full_score_limits_keyboards_by_default():
    gtr = pretty_midi.Instrument(29, name="Guitar")
    gtr.notes = [N(52, 0)]
    assert len(build(_song(), [gtr], []).instruments[1].notes) == 8
    assert len(build(_song(), [gtr], [], keyboard_limit=False).instruments[1].notes) == 72
