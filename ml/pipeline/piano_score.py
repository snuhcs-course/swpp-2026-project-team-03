"""Two-hand notation for the keyboard PDF (scores/piano.pdf).

MuseScore 3's MIDI import splits a piano track between the staves by itself and adds
voices and clef changes as it goes. On transcribed keyboard parts that gave high notes
on the bass staff (four or five ledger lines), both staves switching to treble clef
for a few bars, and stacks of voice rests. Here the hands are decided before MuseScore
sees the notes:

1. snap to a sixteenth grid (the MIDI is already beat-aligned, one tempo);
2. split every onset between the hands with a Viterbi pass that keeps each hand
   within five notes and a fourteen-semitone span, near its usual register, and
   moving little from the previous onset;
3. write each hand as block chords (one end per onset, cut at the next onset,
   short gaps closed), at most four notes in the right hand and three in the left;
4. import the two hands as two single-staff parts with clef changes off, then join
   them into one piano grand staff;
5. switch a staff to the other clef only for runs of at least four bars that clearly
   sit in the other register, and write long runs of very high right-hand notes
   under an 8va line instead of with three or more ledger lines.

Only the PDF changes: scores/piano.mid and the MP3 still come from the original
keyboard tracks. Settings were picked on 31 songs (24 piano/synth experiment MIDIs and
7 pipeline runs) by a readability count (clef changes, voices, rests, ledger lines,
ties, 8va lines per bar; score-lab experiment, 2026-11-27).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pretty_midi

# Bump when the arrangement or the MSCX post-processing changes, so finished runs
# get a new PDF on the next publish instead of keeping the cached one.
NOTATION_VERSION = "two-hand-1"

GRID = 16                 # note value of the onset grid
MIN_STEPS = 0.5           # notes shorter than this many grid steps are dropped
LEGATO_STEPS = 2          # gaps shorter than this many grid steps are closed
MAX_RIGHT, MAX_LEFT = 4, 3
HAND_SPAN = 14            # semitones one hand holds at once
RIGHT_LOW, LEFT_HIGH = 55, 60  # right hand below G3 / left hand above C4 costs extra
REGISTER_WEIGHT = 1.0
MOVE_WEIGHT = 0.35
RIGHT_HOME, LEFT_HOME = 72.0, 50.0
FOLD_RIGHT = (55, 96)     # notes outside are moved by octaves (rare after the split)
FOLD_LEFT = (36, 67)      # left hand below C2 goes up an octave
SECTION_CLEF_BARS = 4
OTTAVA_TRIGGER = 88       # E6: three ledger lines above the treble staff
OTTAVA_FLOOR = 79         # a run continues while its lowest note stays at or above G5
OTTAVA_BRIDGE = 67        # runs this close join if nothing between them is below G4
OTTAVA_MIN = Fraction(1, 4)  # lines shorter than a quarter note are not worth a bracket

# Single-staff, non-transposing GM sounds for the import only (treble and bass clef).
# Track names must not say "piano": MuseScore picks the instrument by name first.
RIGHT_PROGRAM, LEFT_PROGRAM = 73, 70
IMPORT_OPTIONS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                  "<MidiOptions>\n<ClefChanges>false</ClefChanges>\n</MidiOptions>\n")


@dataclass
class Note:
    start: int  # tick
    end: int
    pitch: int
    velocity: int


# ---------------------------------------------------------------- arrangement

def load_notes(score: pretty_midi.PrettyMIDI) -> list[Note]:
    notes = []
    for track in score.instruments:
        if track.is_drum:
            continue
        for n in track.notes:
            start, end = score.time_to_tick(n.start), score.time_to_tick(n.end)
            if end > start:
                notes.append(Note(start, end, n.pitch, n.velocity))
    return notes


def remove_overlaps(notes: list[Note]) -> list[Note]:
    """One sounding copy per pitch: equal starts merge, a later start cuts the earlier note."""
    out: list[Note] = []
    for n in sorted(notes, key=lambda n: (n.pitch, n.start, -n.end)):
        if out and out[-1].pitch == n.pitch and n.start < out[-1].end:
            if n.start == out[-1].start:
                out[-1].end = max(out[-1].end, n.end)
                continue
            out[-1].end = n.start
        out.append(n)
    return sorted(out, key=lambda n: (n.start, n.pitch))


def snap(notes: list[Note], step: int, min_len: int) -> list[Note]:
    snapped = []
    for n in notes:
        if n.end - n.start < min_len:
            continue
        start = round(n.start / step) * step
        snapped.append(Note(start, max(start + step, round(n.end / step) * step), n.pitch, n.velocity))
    return remove_overlaps(snapped)


def onsets(notes: list[Note]) -> list[list[Note]]:
    groups: dict[int, list[Note]] = {}
    for n in notes:
        groups.setdefault(n.start, []).append(n)
    return [sorted(groups[t], key=lambda n: n.pitch) for t in sorted(groups)]


def split_cost(pitches: list[int], k: int) -> tuple[float, float | None, float | None]:
    """Cost of giving pitches[:k] to the left hand and the rest to the right hand."""
    left, right = pitches[:k], pitches[k:]
    cost = 0.0
    for hand, cap in ((left, MAX_LEFT), (right, MAX_RIGHT)):
        if hand:
            cost += 6.0 * max(0, hand[-1] - hand[0] - HAND_SPAN)
            cost += 4.0 * max(0, len(hand) - cap)
    cost += REGISTER_WEIGHT * sum(max(0, RIGHT_LOW - p) for p in right)
    cost += REGISTER_WEIGHT * sum(max(0, p - LEFT_HIGH) for p in left)
    return (cost, sum(left) / len(left) if left else None, sum(right) / len(right) if right else None)


def assign_hands(groups: list[list[Note]]) -> list[int]:
    """Viterbi over onsets. State k = number of lowest notes the left hand takes."""
    back: list[list[int]] = []
    costs: list[float] = []
    centers: list[tuple[float, float]] = []
    for i, group in enumerate(groups):
        pitches = [n.pitch for n in group]
        new_costs, new_centers, new_back = [], [], []
        for k in range(len(pitches) + 1):
            base, lc, rc = split_cost(pitches, k)
            if i == 0:
                new_costs.append(base)
                new_centers.append((lc if lc is not None else LEFT_HOME, rc if rc is not None else RIGHT_HOME))
                new_back.append(-1)
                continue
            best, arg = float("inf"), 0
            for j, prev in enumerate(costs):
                pl, pr = centers[j]
                move = (abs(lc - pl) if lc is not None else 0.0) + (abs(rc - pr) if rc is not None else 0.0)
                cross = (8.0 if lc is not None and lc > pr else 0.0) + (8.0 if rc is not None and rc < pl else 0.0)
                total = prev + base + MOVE_WEIGHT * move + cross
                if total < best:
                    best, arg = total, j
            pl, pr = centers[arg]
            new_costs.append(best)
            new_centers.append((pl if lc is None else (pl + lc) / 2, pr if rc is None else (pr + rc) / 2))
            new_back.append(arg)
        back.append(new_back)
        costs, centers = new_costs, new_centers
    if not groups:
        return []
    k = min(range(len(costs)), key=costs.__getitem__)
    ks = [0] * len(groups)
    for i in range(len(groups) - 1, -1, -1):
        ks[i] = k
        k = back[i][k]
    return ks


def block_chords(hand: list[Note], step: int) -> list[Note]:
    """Every onset becomes one chord with one length: up to its longest note, cut at the
    next onset of the same hand; a gap shorter than LEGATO_STEPS is closed."""
    groups = onsets(hand)
    out = []
    for i, group in enumerate(groups):
        start = group[0].start
        end = max(n.end for n in group)
        if i + 1 < len(groups):
            following = groups[i + 1][0].start
            if end > following or following - end < LEGATO_STEPS * step:
                end = following
        out += [Note(start, max(end, start + step), n.pitch, n.velocity) for n in group]
    return out


def thin(hand: list[Note], cap: int) -> list[Note]:
    """Keep at most `cap` notes per onset: top and bottom first, then new pitch classes."""
    out = []
    for group in onsets(hand):
        if len(group) <= cap:
            out += group
            continue
        chosen = [group[-1], group[0]]
        classes = {n.pitch % 12 for n in chosen}
        for n in sorted(group[1:-1], key=lambda n: (n.pitch % 12 in classes, -n.pitch)):
            if len(chosen) == cap:
                break
            chosen.append(n)
            classes.add(n.pitch % 12)
        out += chosen
    return out


def fold(hand: list[Note], low: int, high: int) -> list[Note]:
    out, seen = [], set()
    for n in hand:
        pitch = n.pitch
        while pitch > high:
            pitch -= 12
        while pitch < low:
            pitch += 12
        if (n.start, pitch) not in seen:
            seen.add((n.start, pitch))
            out.append(Note(n.start, n.end, pitch, n.velocity))
    return out


def arrange(score: pretty_midi.PrettyMIDI) -> tuple[pretty_midi.PrettyMIDI, dict]:
    """All keyboard tracks of `score` as a right-hand and a left-hand track."""
    step = score.resolution * 4 // GRID
    notes = snap(load_notes(score), step, int(MIN_STEPS * step))
    groups = onsets(notes)
    right, left = [], []
    for group, k in zip(groups, assign_hands(groups)):
        left += group[:k]
        right += group[k:]
    right = fold(thin(block_chords(right, step), MAX_RIGHT), *FOLD_RIGHT)
    left = fold(thin(block_chords(left, step), MAX_LEFT), *FOLD_LEFT)

    tempi = score.get_tempo_changes()[1]
    out = pretty_midi.PrettyMIDI(resolution=score.resolution, initial_tempo=float(tempi[0]) if len(tempi) else 120.0)
    out.time_signature_changes = list(score.time_signature_changes)
    out.key_signature_changes = list(score.key_signature_changes)
    for name, program, hand in (("Upper", RIGHT_PROGRAM, right), ("Lower", LEFT_PROGRAM, left)):
        track = pretty_midi.Instrument(program=program, name=name)
        track.notes = [pretty_midi.Note(n.velocity, n.pitch, out.tick_to_time(n.start), out.tick_to_time(n.end))
                       for n in sorted(hand, key=lambda n: (n.start, n.pitch))]
        out.instruments.append(track)
    return out, {"source_notes": len(notes), "right_notes": len(right), "left_notes": len(left)}


# ---------------------------------------------------------------- MSCX

def _clef(kind: str) -> ET.Element:
    clef = ET.Element("Clef")
    ET.SubElement(clef, "concertClefType").text = kind
    ET.SubElement(clef, "transposingClefType").text = kind
    return clef


def _staff_def(staff_id: str, clef: str | None, brace: bool) -> ET.Element:
    staff = ET.Element("Staff", id=staff_id)
    ET.SubElement(ET.SubElement(staff, "StaffType", group="pitched"), "name").text = "stdNormal"
    if brace:
        ET.SubElement(staff, "bracket", type="1", span="2", col="0")
        ET.SubElement(staff, "barLineSpan").text = "1"
    if clef:
        ET.SubElement(staff, "defaultClef").text = clef
    return staff


def section_clefs(body: ET.Element, home: str, min_bars: int = SECTION_CLEF_BARS) -> int:
    """Change to the other clef only over >= min_bars bars that clearly sit in the other
    register; empty bars join a run but never end it. Returns the clef changes added."""
    measures = body.findall("Measure")
    other = "G" if home == "F" else "F"
    flags: list[bool | None] = []
    for measure in measures:
        pitches = sorted(int(n.findtext("pitch") or 0) for n in measure.iter("Note"))
        if not pitches:
            flags.append(None)
            continue
        median = pitches[len(pitches) // 2]
        if home == "F":
            flags.append(median >= 62 and sum(p < 55 for p in pitches) <= len(pitches) // 5)
        else:
            flags.append(median <= 57 and sum(p > 65 for p in pitches) <= len(pitches) // 5)
    added, i = 0, 0
    while i < len(flags):
        if not flags[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(flags) and flags[j + 1] is not False:
            j += 1
        while j > i and flags[j] is None:
            j -= 1
        if sum(1 for f in flags[i:j + 1] if f) >= min_bars:
            measures[i].find("voice").insert(0, _clef(other))
            added += 1
            if j + 1 < len(measures):
                measures[j + 1].find("voice").insert(0, _clef(home))
                added += 1
        i = j + 1
    return added


def join_hands(document: ET.ElementTree, name: str = "Piano", short: str = "Pno.") -> tuple[str, str]:
    """Replace the two single-staff hand parts by one piano part with a grand staff.
    Returns the right- and left-hand staff ids."""
    score = document.getroot().find("Score")
    parts = score.findall("Part")
    if len(parts) != 2 or any(len(part.findall("Staff")) != 1 for part in parts):
        raise ValueError(f"expected two single-staff hand parts, found {[len(p.findall('Staff')) for p in parts]}")
    right, left = parts
    right_id, left_id = right.find("Staff").get("id"), left.find("Staff").get("id")
    piano = ET.Element("Part")
    piano.append(_staff_def(right_id, None, True))
    piano.append(_staff_def(left_id, "F", False))
    ET.SubElement(piano, "trackName").text = name
    instrument = copy.deepcopy(right.find("Instrument"))
    for tag, value in (("longName", name), ("shortName", short), ("trackName", name),
                       ("instrumentId", "keyboard.piano"), ("minPitchP", "21"), ("maxPitchP", "108"),
                       ("minPitchA", "21"), ("maxPitchA", "108")):
        elements = instrument.findall(tag) or [ET.SubElement(instrument, tag)]
        for element in elements:
            element.text = value
    for tag in ("clef", "transposeDiatonic", "transposeChromatic"):
        for element in instrument.findall(tag):
            instrument.remove(element)
    for program in instrument.iter("program"):
        program.set("value", "0")
    piano.append(instrument)
    index = list(score).index(right)
    score.remove(right)
    score.remove(left)
    score.insert(index, piano)
    for staff_id, home in ((right_id, "G"), (left_id, "F")):
        body = next(s for s in score.findall("Staff") if s.get("id") == staff_id)
        for voice in body.iter("voice"):
            for element in [e for e in voice if e.tag == "Clef"]:
                voice.remove(element)
        section_clefs(body, home)
    return right_id, left_id


_LENGTHS = {"breve": Fraction(2), "whole": Fraction(1), "half": Fraction(1, 2), "quarter": Fraction(1, 4),
            "eighth": Fraction(1, 8), "16th": Fraction(1, 16), "32nd": Fraction(1, 32), "64th": Fraction(1, 64),
            "128th": Fraction(1, 128)}


def _length(element: ET.Element, bar: Fraction) -> Fraction:
    kind = element.findtext("durationType") or "quarter"
    if kind == "measure":
        return bar
    length = extra = _LENGTHS[kind]
    for _ in range(int(element.findtext("dots") or 0)):
        extra /= 2
        length += extra
    return length


def _location(measures: int, fraction: Fraction) -> ET.Element:
    location = ET.Element("location")
    if measures:
        ET.SubElement(location, "measures").text = str(measures)
    if fraction:
        ET.SubElement(location, "fractions").text = f"{fraction.numerator}/{fraction.denominator}"
    return location


def add_ottavas(document: ET.ElementTree, staff_id: str) -> int:
    """Write long runs of very high notes an octave lower under an 8va line.
    In MuseScore 3 files <pitch> is the written pitch; the line raises the sound."""
    score = document.getroot().find("Score")
    staff = next(s for s in score.findall("Staff") if s.get("id") == staff_id)
    if staff.find(".//Tuplet") is not None:
        return 0  # positions below ignore tuplet ratios; the sixteenth grid should never make one
    measures = staff.findall("Measure")
    events = []  # (bar index, position in bar, element, voice)
    bars = []    # (start of bar from the top, bar length)
    position, bar = Fraction(0), Fraction(1)
    for index, measure in enumerate(measures):
        for signature in measure.iter("TimeSig"):
            bar = Fraction(int(signature.findtext("sigN")), int(signature.findtext("sigD")))
            break
        bars.append((position, bar))
        position += bar
        voice = measure.find("voice")
        t = Fraction(0)
        for element in list(voice) if voice is not None else []:
            if element.tag in ("Chord", "Rest"):
                events.append((index, t, element, voice))
                t += _length(element, bar)

    def pitches(k: int) -> list[int]:
        return [int(n.findtext("pitch")) for n in events[k][2].findall("Note")]

    def is_chord(k: int) -> bool:
        return events[k][2].tag == "Chord"

    def start(k: int) -> Fraction:
        return bars[events[k][0]][0] + events[k][1]

    def end(k: int) -> Fraction:
        return start(k) + _length(events[k][2], bars[events[k][0]][1])

    runs: list[tuple[int, int]] = []
    k = 0
    while k < len(events):
        if not (is_chord(k) and max(pitches(k)) >= OTTAVA_TRIGGER):
            k += 1
            continue
        first = k
        while first > 0 and is_chord(first - 1) and min(pitches(first - 1)) >= OTTAVA_FLOOR:
            first -= 1
        last, j = k, k + 1
        while j < len(events):
            if is_chord(j):
                if min(pitches(j)) < OTTAVA_FLOOR:
                    break
                last = j
            elif end(j) - end(last) > Fraction(1, 2):  # a long rest ends the run
                break
            j += 1
        if runs and first <= runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], max(last, runs[-1][1]))
        else:
            runs.append((first, last))
        k = last + 1

    joined: list[tuple[int, int]] = []
    for run in runs:
        if joined:
            previous = joined[-1]
            between = range(previous[1] + 1, run[0])
            if (all(not is_chord(b) or min(pitches(b)) >= OTTAVA_BRIDGE for b in between)
                    and events[run[0]][0] - events[previous[1]][0] <= 2):
                joined[-1] = (previous[0], run[1])
                continue
        joined.append(run)
    runs = [run for run in joined if end(run[1]) - start(run[0]) >= OTTAVA_MIN]

    for first, last in runs:
        first_bar, first_t, first_el, first_voice = events[first]
        last_bar, last_t, last_el, last_voice = events[last]
        stop_bar, stop_t = last_bar, last_t + _length(last_el, bars[last_bar][1])
        if stop_t >= bars[last_bar][1]:
            stop_bar, stop_t = last_bar + 1, Fraction(0)
        begin = ET.Element("Spanner", type="Ottava")
        ET.SubElement(ET.SubElement(begin, "Ottava"), "subtype").text = "8va"
        ET.SubElement(begin, "next").append(_location(stop_bar - first_bar, stop_t - first_t))
        first_voice.insert(list(first_voice).index(first_el), begin)
        finish = ET.Element("Spanner", type="Ottava")
        ET.SubElement(finish, "prev").append(_location(first_bar - stop_bar, first_t - stop_t))
        if stop_bar == last_bar:
            last_voice.insert(list(last_voice).index(last_el) + 1, finish)
        elif stop_bar < len(measures):
            measures[stop_bar].find("voice").insert(0, finish)
        else:
            last_voice.append(finish)
        for k in range(first, last + 1):
            for note in events[k][2].findall("Note"):
                note.find("pitch").text = str(int(note.findtext("pitch")) - 12)
    return len(runs)


# ---------------------------------------------------------------- driver

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_key(source: Path) -> str:
    """What the stamp next to the .mscx holds: the MIDI it was made from and how."""
    return f"{_sha256(source)} {NOTATION_VERSION}"


def cached(source: Path, target: Path, suffix: str = "") -> bool:
    stamp = target.with_suffix(target.suffix + ".source_sha256")
    return (target.is_file() and stamp.is_file()
            and stamp.read_text().strip() == (cache_key(source) + suffix).strip())


def piano_notation(source: Path, target: Path, musescore: str, *, force: bool = False) -> dict:
    """Write `target` (.mscx): the keyboard tracks of `source` as a two-hand piano score."""
    stamp = target.with_suffix(target.suffix + ".source_sha256")
    key = cache_key(source)
    if not force and cached(source, target):
        return {"cached": True}
    hands, stats = arrange(pretty_midi.PrettyMIDI(str(source)))
    hands_midi = target.with_name(target.stem + "_hands.mid")
    options = target.with_name(target.stem + "_import.xml")
    imported = target.with_name(target.stem + "_hands.mscx")
    hands.write(str(hands_midi))
    options.write_text(IMPORT_OPTIONS, encoding="utf-8")
    try:
        subprocess.run([musescore, "-M", str(options), "-o", str(imported), str(hands_midi)], check=True)
        document = ET.parse(imported)
        right_id, _ = join_hands(document)
        stats["ottavas"] = add_ottavas(document, right_id)
        document.write(target, encoding="utf-8", xml_declaration=True)
    finally:
        for path in (hands_midi, options, imported):
            path.unlink(missing_ok=True)
    stamp.write_text(key + "\n", encoding="ascii")
    return stats
