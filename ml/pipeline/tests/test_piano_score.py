"""Two-hand keyboard notation: arrangement and MSCX post-processing (no MuseScore needed)."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import piano_score
import publish_scores
from piano_score import (MAX_LEFT, MAX_RIGHT, Note, add_ottavas, arrange, block_chords, join_hands,
                         section_clefs, thin)


def keyboard(notes, tempo=120.0):
    """notes: (pitch, start_beat, end_beat) on one keyboard track."""
    score = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    score.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0)]
    track = pretty_midi.Instrument(program=0, name="piano: piano")
    beat = 60.0 / tempo
    for pitch, start, end in notes:
        track.notes.append(pretty_midi.Note(90, pitch, start * beat, end * beat))
    score.instruments.append(track)
    return score


def test_bass_and_melody_go_to_their_own_hands():
    notes = []
    for beat in range(8):
        notes += [(36 + (beat % 2) * 7, beat, beat + 1),          # bass C2/G2
                  (72, beat, beat + 1), (76, beat, beat + 1), (79, beat, beat + 1)]  # C major on top
    hands, stats = arrange(keyboard(notes))
    upper, lower = hands.instruments
    assert (upper.name, lower.name) == ("Upper", "Lower")
    assert (upper.program, lower.program) == (piano_score.RIGHT_PROGRAM, piano_score.LEFT_PROGRAM)
    assert {n.pitch for n in upper.notes} == {72, 76, 79}
    assert {n.pitch for n in lower.notes} == {36, 43}
    assert stats["right_notes"] + stats["left_notes"] == len(notes)


def test_hands_never_exceed_their_note_caps():
    cluster = [(p, 0, 1) for p in (40, 45, 50, 55, 60, 64, 67, 72, 76, 79, 84)]
    hands, _ = arrange(keyboard(cluster))
    upper, lower = hands.instruments
    assert len(upper.notes) <= MAX_RIGHT
    assert len(lower.notes) <= MAX_LEFT
    assert max(n.pitch for n in lower.notes) < min(n.pitch for n in upper.notes)


def test_block_chords_share_one_end_and_close_small_gaps():
    step = 120
    hand = [Note(0, 300, 60, 90), Note(0, 480, 64, 90),   # same onset, different lengths
            Note(600, 900, 62, 90),                       # next onset after a 1-step gap
            Note(2400, 2520, 65, 90)]                     # far away: the gap stays a rest
    out = sorted(block_chords(hand, step), key=lambda n: (n.start, n.pitch))
    first = [n for n in out if n.start == 0]
    assert {n.end for n in first} == {600}  # longest note (480) extended over the short gap to 600
    second = next(n for n in out if n.start == 600)
    assert second.end == 900                # 1500 ticks to the next onset: not closed


def test_thin_keeps_outer_notes_and_new_pitch_classes():
    chord = [Note(0, 480, p, 90) for p in (60, 64, 67, 72, 76)]  # C E G C E
    kept = sorted(n.pitch for n in thin(chord, 3))
    assert kept[0] == 60 and kept[-1] == 76
    assert len(kept) == 3 and {p % 12 for p in kept} == {0, 4, 7}


def mscx(parts_pitches, measures=6, kind="quarter"):
    """A MuseScore 3 file with one single-staff part per entry of parts_pitches
    (pitches[bar] = list of quarter-note pitches; [] = whole rest)."""
    root = ET.Element("museScore", version="3.01")
    score = ET.SubElement(root, "Score")
    for i, _ in enumerate(parts_pitches, start=1):
        part = ET.SubElement(score, "Part")
        staff = ET.SubElement(part, "Staff", id=str(i))
        ET.SubElement(ET.SubElement(staff, "StaffType", group="pitched"), "name").text = "stdNormal"
        ET.SubElement(part, "trackName").text = f"hand {i}"
        instrument = ET.SubElement(part, "Instrument")
        ET.SubElement(instrument, "longName").text = f"hand {i}"
        ET.SubElement(instrument, "clef").text = "G"
        channel = ET.SubElement(instrument, "Channel")
        ET.SubElement(channel, "program", value="73")
    for i, bars in enumerate(parts_pitches, start=1):
        body = ET.SubElement(score, "Staff", id=str(i))
        for b in range(measures):
            measure = ET.SubElement(body, "Measure")
            voice = ET.SubElement(measure, "voice")
            if b == 0:
                clef = ET.SubElement(voice, "Clef")
                ET.SubElement(clef, "concertClefType").text = "G"
                sig = ET.SubElement(voice, "TimeSig")
                ET.SubElement(sig, "sigN").text = "4"
                ET.SubElement(sig, "sigD").text = "4"
            pitches = bars[b] if b < len(bars) else []
            if not pitches:
                rest = ET.SubElement(voice, "Rest")
                ET.SubElement(rest, "durationType").text = "measure"
                continue
            for pitch in pitches:
                chord = ET.SubElement(voice, "Chord")
                ET.SubElement(chord, "durationType").text = kind
                note = ET.SubElement(chord, "Note")
                ET.SubElement(note, "pitch").text = str(pitch)
    return ET.ElementTree(root)


def test_join_hands_makes_one_grand_staff_without_clef_changes():
    doc = mscx([[[72] * 4] * 6, [[48] * 4] * 6])
    right, left = join_hands(doc)
    score = doc.getroot().find("Score")
    parts = score.findall("Part")
    assert len(parts) == 1
    staves = parts[0].findall("Staff")
    assert [s.get("id") for s in staves] == [right, left] == ["1", "2"]
    assert staves[0].find("bracket") is not None
    assert staves[1].findtext("defaultClef") == "F"
    assert parts[0].find("Instrument").findtext("longName") == "Piano"
    assert parts[0].find("Instrument").find("clef") is None
    assert not list(score.iter("Clef"))  # import clefs removed, nothing in another register


def test_left_hand_gets_treble_clef_only_for_long_high_sections():
    high, low = [67] * 4, [43] * 4
    body = mscx([[low, high, high, high, high, low]], measures=6).getroot().find("Score").findall("Staff")[0]
    assert section_clefs(body, "F", 4) == 2
    clefs = [(i, c.findtext("concertClefType")) for i, m in enumerate(body.findall("Measure"))
             for c in m.iter("Clef") if c.findtext("concertClefType") in "GF"]
    assert (1, "G") in clefs and (5, "F") in clefs
    short = mscx([[low, high, high, low, low, low]], measures=6).getroot().find("Score").findall("Staff")[0]
    assert section_clefs(short, "F", 4) == 0


def test_long_high_runs_go_under_an_8va_line_and_are_written_lower():
    doc = mscx([[[72] * 4, [91, 93, 91, 89], [91] * 4, [72] * 4]], measures=4)
    assert add_ottavas(doc, "1") == 1
    body = doc.getroot().find("Score").findall("Staff")[0]
    second = body.findall("Measure")[1].find("voice")
    assert second[0].tag == "Spanner" and second[0].get("type") == "Ottava"
    assert second[0].find("Ottava").findtext("subtype") == "8va"
    assert [int(n.findtext("pitch")) for n in second.iter("Note")] == [79, 81, 79, 77]
    third_bar = body.findall("Measure")[2].find("voice")
    assert [int(n.findtext("pitch")) for n in third_bar.iter("Note")] == [79] * 4
    end = body.findall("Measure")[3].find("voice")[0]
    assert end.tag == "Spanner" and end.find("prev") is not None
    assert end.find("prev/location/measures").text == "-2"


def test_a_short_high_note_keeps_its_ledger_lines():
    doc = mscx([[[72, 72, 91, 72, 72, 72, 72, 72]]], measures=1, kind="eighth")
    assert add_ottavas(doc, "1") == 0  # one eighth note is not worth an 8va bracket
    assert 91 in [int(n.findtext("pitch")) for n in doc.getroot().iter("Note")]


def test_keyboard_pdf_falls_back_to_musescore_import(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("no hands")
    calls = []
    monkeypatch.setattr(piano_score, "piano_notation", broken)
    def fake_import(source, target, musescore, force=False):
        calls.append((source, target, force))
        target.write_text("<museScore/>")
    monkeypatch.setattr(publish_scores, "musescore_score", fake_import)
    source, target = tmp_path / "piano.mid", tmp_path / "piano_render.mscx"
    source.write_bytes(b"MThd")
    publish_scores.keyboard_notation(source, target, "musescore3")
    assert calls == [(source, target, True)]
    publish_scores.keyboard_notation(source, target, "musescore3")  # same MIDI: no new attempt
    assert len(calls) == 1
    source.write_bytes(b"MThd changed")
    publish_scores.keyboard_notation(source, target, "musescore3")
    assert len(calls) == 2
