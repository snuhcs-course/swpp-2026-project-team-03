"""refine_positions (open-string / far-note fix) and beat_pieces (GP5 durations cut at beats).

Cases come from the 2026-11 band-player interviews:
- bass: D-string open <-> A-string open back and forth inside a 5th-position line (17-18마디)
- guitar: one note put on the 12th fret between low-position notes (운지 왔다갔다)
- bass reader: "1박씩 끊어서" -> a note must not hide a beat
"""
import guitarpro as gp
import pretty_midi
import pytest

import skyline_tab as st
from skyline_tab import beat_pieces, refine_positions, write_gp5


def _tab(events, strings):
    """tuttut-like tab dict: events = [(time, [(string, fret), ...])]."""
    return {"tuning": strings, "measures": [{"events": [
        {"time": t, "time_ticks": int(t * 960), "notes": [{"string": s, "fret": f} for s, f in sf]}
        for t, sf in events]}]}


def _positions(tab):
    return [[(n["string"], n["fret"]) for n in e["notes"]] for e in tab["measures"][0]["events"]]


def _pitches(tab, strings):
    return [[strings[n["string"]] + n["fret"] for n in e["notes"]] for e in tab["measures"][0]["events"]]


BASS = [43, 38, 33, 28]          # G2 D2 A1 E1, thin -> thick
GUITAR = st.TUNINGS["standard"]


def test_open_string_back_and_forth_moves_to_fifth_position():
    # A-string 5 (D2), then D open / A open alternating, then A-string 3, 5
    events = [(0.0, [(2, 5)]), (0.25, [(1, 0)]), (0.5, [(2, 0)]), (0.75, [(1, 0)]),
              (1.0, [(2, 0)]), (1.25, [(2, 3)]), (1.5, [(2, 5)])]
    tab = _tab(events, BASS)
    before = _pitches(tab, BASS)
    st_ = refine_positions(tab, BASS)
    assert _pitches(tab, BASS) == before                     # same sounding notes
    assert all(f > 0 for e in _positions(tab) for _, f in e)  # no open strings left
    assert _positions(tab)[1:5] == [[(2, 5)], [(3, 5)], [(2, 5)], [(3, 5)]]
    assert st_["open_moved"] == 4


def test_far_single_note_comes_back_to_the_hand():
    # E3 written on the 6th string 12th fret between 2nd-5th fret notes -> D string 2
    events = [(0.0, [(4, 2)]), (0.25, [(4, 3)]), (0.5, [(5, 12)]), (0.75, [(4, 5)]), (1.0, [(4, 3)])]
    tab = _tab(events, GUITAR)
    refine_positions(tab, GUITAR)
    assert _positions(tab)[2] == [(3, 2)]


def test_open_string_riff_alone_is_left_alone():
    # low-E chug riff: no fretted neighbour except the 3rd fret note; the open E has no other spot
    events = [(k * 0.25, [(5, 0)]) for k in range(6)] + [(1.5, [(5, 3)])]
    tab = _tab(events, GUITAR)
    before = _positions(tab)
    refine_positions(tab, GUITAR)
    assert _positions(tab) == before


def test_no_fretted_neighbour_means_no_change():
    events = [(0.0, [(1, 0)]), (0.5, [(0, 0)]), (1.0, [(2, 0)])]
    tab = _tab(events, GUITAR)
    before = _positions(tab)
    assert sum(refine_positions(tab, GUITAR).values()) == 0
    assert _positions(tab) == before


def test_long_rest_resets_the_hand():
    # the fretted note is 5 s away: not a neighbour, so the open string stays
    events = [(0.0, [(2, 7)]), (5.0, [(1, 0)])]
    tab = _tab(events, GUITAR)
    refine_positions(tab, GUITAR)
    assert _positions(tab)[1] == [(1, 0)]


def test_chord_note_stays_when_its_other_strings_are_taken():
    # A5 power chord (6th string 5, 5th string 7) + open D: D2's fretted spots (5th string 5,
    # 6th string 10) are both on strings the chord already uses, so the open D stays
    events = [(0.0, [(5, 5), (4, 7)]), (0.5, [(5, 5), (4, 7), (3, 0)]), (1.0, [(5, 5), (4, 7)])]
    tab = _tab(events, GUITAR)
    refine_positions(tab, GUITAR)
    assert _positions(tab)[1] == [(5, 5), (4, 7), (3, 0)]


def test_chord_note_never_breaks_the_chord_shape():
    # open G (G3) over fretted notes at frets 8-10: its only free fretted spot (D string 5) would make the
    # chord span 5 frets > MAX_SPAN, so whatever happens the chord must stay playable and sound the same
    events = [(0.0, [(5, 8), (4, 10)]), (0.5, [(5, 8), (4, 10), (2, 0)]), (1.0, [(5, 8), (4, 10)])]
    tab = _tab(events, GUITAR)
    before = _pitches(tab, GUITAR)
    refine_positions(tab, GUITAR)
    chord = _positions(tab)[1]
    assert _pitches(tab, GUITAR) == before
    assert len({s for s, _ in chord}) == 3
    fretted = [f for _, f in chord if f > 0]
    assert max(fretted) - min(fretted) <= st.MAX_SPAN


def test_tab_refine_flag_changes_the_text_tab(tmp_path):
    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(29)
    for k, p in enumerate([52, 50, 45, 50, 45, 50, 47, 48]):
        inst.notes.append(pretty_midi.Note(100, p, k * 0.25, k * 0.25 + 0.25))
    pm.instruments.append(inst)
    raw, _ = st.tab(pm, "raw", "standard", tmp_path, refine=False)
    fixed, t = st.tab(pm, "fixed", "standard", tmp_path, refine=True)
    assert raw.read_text() != fixed.read_text()
    frets = [n["fret"] for m in t.tab["measures"] for e in m["events"] for n in e.get("notes", [])]
    assert max(frets) <= 5          # tuttut's E3 on the 12th fret came back to first position


# ----------------------------------------------------------------------
# beat_pieces
# ----------------------------------------------------------------------
@pytest.mark.parametrize("pos,length,beat16,bar16,expected", [
    (0, 16, 4, 16, [16]),            # whole note on beat 1
    (0, 12, 4, 16, [12]),            # dotted half on beat 1
    (8, 8, 4, 16, [8]),              # half note from the middle of the bar
    (4, 8, 4, 16, [4, 4]),           # half note from beat 2 hides beat 3 -> two tied quarters
    (1, 8, 4, 16, [3, 4, 1]),        # off-beat start: to the beat, then beat by beat
    (2, 4, 4, 16, [2, 2]),           # off-beat quarter -> eighth + eighth across the beat
    (6, 12, 6, 24, [6, 6]),          # 12/8: dotted half from beat 2 -> two dotted quarters
    (0, 12, 6, 24, [12]),            # 12/8: dotted half on beat 1
    (0, 12, 6, 12, [12]),            # 6/8: whole bar is one dotted half
    (0, 18, 6, 18, [12, 6]),         # 9/8: whole bar -> dotted half + dotted quarter, cut at beat 3
    (0, 24, 6, 24, [12, 12]),        # 12/8: whole bar -> two dotted halves, cut at beat 3
    (0, 12, 4, 12, [12]),            # 3/4: whole bar is one dotted half
])
def test_beat_pieces(pos, length, beat16, bar16, expected):
    pieces = beat_pieces(pos, length, beat16, bar16)
    assert [L for L, _, _ in pieces] == expected
    assert sum(L for L, _, _ in pieces) == length


@pytest.mark.parametrize("pos", range(16))
@pytest.mark.parametrize("length", range(1, 17))
def test_no_piece_crosses_a_beat_unless_it_starts_on_one(pos, length):
    if pos + length > 16:
        return
    at = pos
    for L, _, _ in beat_pieces(pos, length, 4, 16):
        if at % 4:
            assert (at % 4) + L <= 4
        at += L


def test_gp5_off_beat_half_note_is_written_tied(tmp_path):
    path = tmp_path / "b.gp5"
    write_gp5(path, "t", 120, 4, "standard", [("g", [(1, 8, [(1, 3)])])])
    beats = gp.parse(str(path)).tracks[0].measures[0].voices[0].beats
    lengths = [{1: 16, 2: 8, 4: 4, 8: 2, 16: 1}[b.duration.value] * (1.5 if b.duration.isDotted else 1)
               for b in beats]
    assert lengths == [1, 3, 4, 1, 3, 4]       # 16th rest, dotted 8th, quarter (tie), 16th (tie), rests
    assert [b.notes[0].type for b in beats[1:4]] == [gp.NoteType.normal, gp.NoteType.tie, gp.NoteType.tie]


@pytest.mark.parametrize("num,expected", [(9, [6, 3]), (12, [6, 6])])
def test_gp5_compound_whole_bar_note_is_cut_at_a_beat(tmp_path, num, expected):
    """A note filling a 9/8 or 12/8 bar is tied at the dotted-quarter beat, not after 16 16ths."""
    path = tmp_path / "c.gp5"
    write_gp5(path, "t", 120, num, "standard", [("g", [(0, num * 2, [(1, 3)])])], 8)
    beats = gp.parse(str(path)).tracks[0].measures[0].voices[0].beats
    eighths = [{1: 8, 2: 4, 4: 2, 8: 1}[b.duration.value] * (1.5 if b.duration.isDotted else 1)
               for b in beats]
    assert eighths == expected
    assert [b.notes[0].type for b in beats] == [gp.NoteType.normal, gp.NoteType.tie]


def test_open_strings_in_first_position_stay():
    # hand around fret 2: open A and open D are normal first-position notes
    events = [(0.0, [(4, 2)]), (0.25, [(4, 0)]), (0.5, [(3, 2)]), (0.75, [(3, 0)]), (1.0, [(4, 3)])]
    tab = _tab(events, GUITAR)
    before = _positions(tab)
    refine_positions(tab, GUITAR)
    assert _positions(tab) == before
