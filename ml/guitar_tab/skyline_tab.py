"""Skyline baseline for guitar TAB.

MuScriptor often merges two guitars into one part. This script
1. picks a tuning (standard / half step down / drop D) from the lowest notes,
2. decides whether the part holds two guitars (auto mode, `decide_split`) and, if so, splits it with the
   skyline rule: the highest note at each onset -> lead, the rest -> rhythm; otherwise keeps one guitar part,
3. makes chords playable (max 6 notes, fretted notes within 4 frets) in the rhythm part and
   the merged part, by default; --no-chord-reduction turns this off,
4. chooses string/fret with tuttut (Viterbi over fingerings, b=0.1), then moves notes tuttut put on an
   open string or far from the hand to a fretted spot near the hand (`refine_positions`; --no-refine turns it off),
5. writes MIDI, text TAB, Guitar Pro (.gp5) files and tuning.json (the tuning used), and reports fret jumps > 5.
   GP5 durations are cut at beat boundaries (with ties), so every beat starts a new note or rest.

Comparison baseline only, not the team's guitar-guitar separation module.
The skyline rule comes from melody-extraction research; the tuning, chord-reduction and
jump-count rules are our own choices.

    python skyline_tab.py song_aligned.mid out_dir/ [--split auto|always|never] [--no-merged] [--no-chord-reduction]

Input: beat-aligned MIDI from ml/beat_align. --no-merged skips the merged-part TAB when the part is split.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import argparse
import collections
import itertools
import json
from pathlib import Path

import numpy as np
import pretty_midi

np.seterr(all="ignore")

TUNINGS = {  # thin -> thick, MIDI numbers
    "standard": [64, 59, 55, 50, 45, 40],
    "half_step_down": [63, 58, 54, 49, 44, 39],
    "drop_d": [64, 59, 55, 50, 45, 38],
}
NAMES = {k: [pretty_midi.note_number_to_name(p) for p in v] for k, v in TUNINGS.items()}
NFRETS = 20
MAX_SPAN = 4          # fretted notes of one chord must fit in 4 frets (open strings free)
SPLIT_MIN_UNPLAYABLE = 0.02   # auto split: >= 2% of onsets cannot be fingered as one chord ...
SPLIT_MIN_WIDE = 0.03         # ... and >= 3% of onsets span more than two octaves (two guitars in two registers)
WIDE_SPAN = 24                # two octaves: E2 (6th string open) to E4 (1st string open)
TB_WEIGHTS = dict(b=0.1, height=1, length=1, n_changed_strings=1)
# refine_positions (2026-11 user interviews: open-string back-and-forth, far position jumps)
HAND_CONTEXT = 4      # fretted events before/after an event that set the hand position
HAND_MAX_GAP = 2.0    # ... only within this many seconds (a long rest resets the hand)
HAND_REACH = 3        # a fretted spot this close to the hand needs no shift
OPEN_COST = 3.0       # an open string costs like a fret this far from the hand ...
OPEN_POSITION = 4     # ... but is free while the hand is at or below this fret (first-position playing)
STRING_COST = 0.5     # per string crossed from the previous single note
MIN_GAIN = 1.0        # move a note only when its cost drops by at least this much


def guitar_notes(pm):
    gs = [i for i in pm.instruments if 24 <= i.program <= 31 and not i.is_drum]
    return sorted((n for i in gs for n in i.notes), key=lambda n: (n.start, n.pitch))


def write_tuning(out_dir, tuning):
    """tuning.json in out_dir: the tuning the TAB uses, for later stages (score PDF text, app display).
    strings are listed low -> high, as players read a tuning (e.g. "D#2 G#2 C#3 F#3 A#3 D#4")."""
    low_to_high = TUNINGS[tuning][::-1]
    info = {"tuning": tuning,
            "standard": tuning in ("standard", "bass_standard", "bass5_standard"),
            "strings": [pretty_midi.note_number_to_name(p) for p in low_to_high],
            "midi": low_to_high}
    (Path(out_dir) / "tuning.json").write_text(json.dumps(info) + "\n")
    return info


def choose_tuning(pitches):
    """Lowest tuning that covers >= 99% of notes; prefer standard when tied."""
    p = np.array(pitches)
    for name in ("standard", "half_step_down", "drop_d"):
        if (p >= min(TUNINGS[name])).mean() >= 0.99:
            return name
    return "half_step_down" if (p >= 39).mean() >= (p >= 38).mean() - 0.005 else "drop_d"


def fold_range(pitch, tuning):
    lo, hi = min(TUNINGS[tuning]), max(TUNINGS[tuning]) + NFRETS
    while pitch < lo:
        pitch += 12
    while pitch > hi:
        pitch -= 12
    return pitch


def fingerings(pitches, tuning):
    """All (string, fret) assignments: one note per string, fretted notes within MAX_SPAN."""
    strings = TUNINGS[tuning]
    opts = [[(s, p - sp) for s, sp in enumerate(strings) if 0 <= p - sp <= NFRETS] for p in pitches]
    for combo in itertools.product(*opts):
        if len({s for s, _ in combo}) < len(combo):
            continue
        fretted = [f for _, f in combo if f > 0]
        if not fretted or max(fretted) - min(fretted) <= MAX_SPAN:
            yield combo


def playable(pitches, tuning):
    return next(fingerings(sorted(set(pitches)), tuning), None) is not None


def reduce_chord(pitches, tuning):
    """Keep lowest and highest; drop inner notes until a playable shape exists (max 6)."""
    ps = sorted(set(pitches))
    while len(ps) > 6:
        ps.pop(len(ps) // 2)
    while len(ps) > 1 and not playable(ps, tuning):
        if len(ps) > 2:
            ps.pop(len(ps) // 2)
        else:            # two notes too far apart: keep the lower one
            ps.pop()
    return ps


def reduce_chords(notes, tuning):
    """Merged part: fold into range, then reduce each onset's chord with reduce_chord.

    Notes with the same pitch at the same onset become one note (the longer end is kept).
    """
    groups = collections.OrderedDict()
    for n in notes:
        groups.setdefault(round(n.start, 4), []).append(n)
    out, stats = [], collections.Counter()
    for grp in groups.values():
        ends = {}
        for n in grp:
            p = fold_range(n.pitch, tuning)
            ends[p] = max(ends.get(p, 0.0), n.end)
        kept = reduce_chord(list(ends), tuning) if len(ends) > 1 else list(ends)
        stats["notes_in"] += len(ends)
        stats["notes_dropped"] += len(ends) - len(kept)
        out += [pretty_midi.Note(100, p, grp[0].start, ends[p]) for p in kept]
    return out, stats


def decide_split(notes, tuning):
    """Auto mode: does this guitar part hold two guitars playing different things?

    Checked before chord reduction (after reduction every chord is playable). Returns (split, stats):
    - unplayable = share of onsets whose notes can't be fingered one per string within 4 frets
    - wide = share of onsets whose lowest and highest notes are more than two octaves apart
    Split only when both are high. Unplayable but narrow = one guitar with extra notes (chord reduction
    fixes it). Recalibrated for BS-RoFormer stems on 13 songs (2026-11-09): two guitars -> unplayable >= 2.9%
    and wide >= 4.4%; one guitar -> wide <= 0.6%. (The 2026-10-30 Demucs calibration, 5% and 6%, judged
    한 페이지가 될 수 있게 (2.9%, 9.8%) as one guitar.) The pipeline also checks the guitar stem's stereo
    image before this (ml/pipeline/rule_gates.py) and forces a split when two guitars are panned apart.
    """
    groups = collections.OrderedDict()
    for n in notes:
        groups.setdefault(round(n.start, 4), set()).add(fold_range(n.pitch, tuning))
    if not groups:
        return False, {"onsets": 0, "unplayable": 0.0, "wide": 0.0}
    unplayable = sum(1 for ps in groups.values() if len(ps) > 1 and not playable(sorted(ps), tuning))
    wide = sum(1 for ps in groups.values() if max(ps) - min(ps) > WIDE_SPAN)
    stats = {"onsets": len(groups), "unplayable": unplayable / len(groups), "wide": wide / len(groups)}
    return stats["unplayable"] >= SPLIT_MIN_UNPLAYABLE and stats["wide"] >= SPLIT_MIN_WIDE, stats


def split_and_clean(notes, tuning, chord_reduction=True):
    groups = collections.OrderedDict()
    for n in notes:
        groups.setdefault(round(n.start, 4), []).append(n)
    lead, rhythm = [], []
    stats = collections.Counter()
    for t, grp in groups.items():
        grp = sorted(grp, key=lambda n: n.pitch)
        top = grp[-1]
        lead.append(pretty_midi.Note(100, fold_range(top.pitch, tuning), top.start, top.end))
        rest = grp[:-1]
        if rest:
            ps = [fold_range(n.pitch, tuning) for n in rest]
            kept = reduce_chord(ps, tuning) if chord_reduction else sorted(set(ps))
            stats["rhythm_notes_in"] += len(set(ps))
            stats["rhythm_notes_dropped"] += len(set(ps)) - len(kept)
            end = max(n.end for n in rest)
            rhythm += [pretty_midi.Note(100, p, t, end) for p in kept]
    # lead is monophonic: cut each note at the next lead onset
    for a, b in zip(lead, lead[1:]):
        a.end = min(a.end, b.start)
    stats["lead_notes"] = len(lead)
    stats["rhythm_notes"] = len(rhythm)
    return lead, rhythm, stats


def part_midi(pm_like, notes, name, program=29):
    out = pretty_midi.PrettyMIDI(initial_tempo=pm_like.get_tempo_changes()[1][0], resolution=pm_like.resolution)
    out.time_signature_changes = pm_like.time_signature_changes
    inst = pretty_midi.Instrument(program=program, name=name)
    inst.notes = notes
    out.instruments.append(inst)
    return out


def tab(midi, name, tuning, out_dir, refine=True):
    from tuttut.logic.tab import Tab
    from tuttut.logic.theory import Tuning
    t = Tab(name, Tuning(NAMES[tuning]), midi, output_dir=str(out_dir), weights=TB_WEIGHTS)
    if refine:
        st = refine_positions(t.tab, TUNINGS[tuning])
        print(f"  refine {name}: {st['open_moved']} open-string notes and {st['jump_moved']} far notes "
              f"moved to the hand position")
    t.to_ascii()
    return (Path(out_dir) / name).with_suffix(".txt"), t


def _hand(frets_by_event, times, i):
    """Median fret of the fretted notes in up to HAND_CONTEXT events before and after event i
    (within HAND_MAX_GAP seconds). None when there is no fretted neighbour."""
    near = []
    for step in (-1, 1):
        j, seen = i + step, 0
        while 0 <= j < len(frets_by_event) and seen < HAND_CONTEXT and abs(times[j] - times[i]) <= HAND_MAX_GAP:
            fretted = [f for f in frets_by_event[j] if f > 0]
            if fretted:
                near += fretted
                seen += 1
            j += step
    return float(np.median(near)) if near else None


def _cost(string, fret, hand, prev_string):
    if fret == 0:
        c = 0.0 if hand <= OPEN_POSITION else OPEN_COST
    else:
        c = max(0.0, abs(fret - hand) - HAND_REACH)
    return c + (STRING_COST * abs(string - prev_string) if prev_string is not None else 0.0)


def refine_positions(tab_dict, strings, passes=3):
    """Move notes to a fretted spot near the hand, in place on tuttut's tab dict.

    tuttut scores an open string as free (it has no height and does not change the hand), so it picks
    open strings even inside a fretted passage (D open <-> A open back and forth on bass) and sometimes
    a far spot for one note (E3 on the 12th fret between 5th-position notes). For each note:
    hand = median fret of the fretted neighbours; cost = OPEN_COST for an open string when the hand is above
    OPEN_POSITION (in first position open strings are normal and cost 0), otherwise the distance beyond
    HAND_REACH frets from the hand, + STRING_COST per string crossed from the previous
    single note. The note moves to the cheapest spot of the same pitch when that saves MIN_GAIN.
    Chord notes may only move to a free string and only if the chord's fretted notes stay within MAX_SPAN.
    No fretted neighbour (an open-string riff on its own) -> left as tuttut wrote it.
    Runs up to `passes` times, because a moved note changes its neighbours' hand position.
    strings: the tuning, thin -> thick (tuttut string 0 = thinnest).
    """
    events = [e for m in tab_dict["measures"] for e in m["events"] if e.get("notes")]
    times = [e["time"] for e in events]
    frets = [[n["fret"] for n in e["notes"]] for e in events]
    stats = collections.Counter(open_moved=0, jump_moved=0)
    for _ in range(passes):
        before = sum(stats.values())
        _refine_pass(events, times, frets, strings, stats)
        if sum(stats.values()) == before:
            break
    return stats


def _refine_pass(events, times, frets, strings, stats):
    prev_string = None
    for i, e in enumerate(events):
        hand = _hand(frets, times, i)
        notes = e["notes"]
        if hand is not None:
            for n in notes:
                pitch = strings[n["string"]] + n["fret"]
                used = {m["string"] for m in notes if m is not n}
                ref = prev_string if len(notes) == 1 else None
                now = _cost(n["string"], n["fret"], hand, ref)
                best = (now, n["string"], n["fret"])
                for s, sp in enumerate(strings):
                    f = pitch - sp
                    if s in used or not 0 <= f <= NFRETS or (s, f) == (n["string"], n["fret"]):
                        continue
                    others = [m["fret"] for m in notes if m is not n and m["fret"] > 0]
                    if f > 0 and others and max(others + [f]) - min(others + [f]) > MAX_SPAN:
                        continue
                    c = _cost(s, f, hand, ref)
                    if c < best[0]:
                        best = (c, s, f)
                if best[0] <= now - MIN_GAIN:
                    stats["open_moved" if n["fret"] == 0 else "jump_moved"] += 1
                    n["string"], n["fret"] = best[1], best[2]
            frets[i] = [n["fret"] for n in notes]
        prev_string = notes[0]["string"] if len(notes) == 1 else None
    return stats


def jump_stats(tab_path):
    """Count fret jumps > 5 between consecutive fretted events (all strings)."""
    lines = [l.split("||", 1)[1] if "||" in l else l for l in tab_path.read_text().splitlines() if l.strip()]
    width = max(len(l) for l in lines)
    events = []
    col = 0
    while col < width:
        frets = []
        nxt = col + 1
        for l in lines:
            if col < len(l) and l[col].isdigit():
                j = col
                while j < len(l) and l[j].isdigit():
                    j += 1
                frets.append(int(l[col:j]))
                nxt = max(nxt, j)
        if frets:
            events.append(frets)
            col = nxt
        else:
            col += 1
    pos = [np.mean([f for f in e if f > 0]) for e in events if any(f > 0 for f in e)]
    jumps = np.abs(np.diff(pos))
    return len(pos), int((jumps > 5).sum()), float(np.median(jumps)) if len(jumps) else 0.0


# ----------------------------------------------------------------------
# Guitar Pro (.gp5) export: keeps tuttut's string/fret choices
# ----------------------------------------------------------------------
GP_LENGTHS = [(16, 1, False), (12, 2, True), (8, 2, False), (6, 4, True),
              (4, 4, False), (3, 8, True), (2, 8, False), (1, 16, False)]  # (16ths, value, dotted)
GP_SINGLE = {L for L, _, _ in GP_LENGTHS}  # lengths one GP5 note value can show


def beat_pieces(pos, length, beat16, bar16):
    """Cut a note or rest that starts pos 16ths into the bar into pieces that do not hide a beat.

    The first piece runs only to the next beat. From a beat, whole beats are kept together only as a
    half bar (from beat 1 or the middle of a 4-beat bar), a whole bar that one note value can show
    (not 9/8 or 12/8: those are kept as dotted halves from odd beats), or a dotted half from beat 1;
    everything else is tied beat by beat. Within a beat split_len picks the values.
    Players read the beat from where each note starts (user interview 2026-11: write it beat by beat).
    Returns [(16ths, value, dotted)] like split_len.
    """
    out = []
    beats_in_bar = bar16 // beat16
    while length > 0:
        off = pos % beat16
        if off:
            take = min(length, beat16 - off)
        else:
            whole, bi = length // beat16, pos // beat16
            if whole == 0:
                take = length
            else:
                n = 1
                if bi == 0 and whole >= beats_in_bar and beats_in_bar in (2, 3, 4) and bar16 in GP_SINGLE:
                    n = beats_in_bar
                elif bi == 0 and whole >= 3 and beats_in_bar == 4 and beat16 == 4:
                    n = 3
                elif bi % 2 == 0 and whole >= 2 and beats_in_bar >= 2 and bi + 2 <= beats_in_bar:
                    n = 2
                take = n * beat16
        out += split_len(take)
        pos += take
        length -= take
    return out


def split_len(n):
    out = []
    while n > 0:
        for L, v, d in GP_LENGTHS:
            if L <= n:
                out.append((L, v, d))
                n -= L
                break
    return out


def track_events(tab_obj, part_notes, ticks_per_16th):
    """[(start16, len16, [(gp_string, fret)])] from tuttut's tab; lengths from the part's notes."""
    ends = collections.defaultdict(float)
    for n in part_notes:
        k = round(n.start, 4)
        ends[k] = max(ends[k], n.end)
    ev = []
    for m in tab_obj.tab["measures"]:
        for e in m["events"]:
            if e.get("notes"):
                ev.append((int(round(e["time_ticks"] / ticks_per_16th)), e["time"],
                           sorted({(nn["string"] + 1, nn["fret"]) for nn in e["notes"]})))
    ev.sort()
    out = []
    for i, (s16, t, sf) in enumerate(ev):
        nxt = ev[i + 1][0] if i + 1 < len(ev) else None
        end_t = ends.get(round(t, 4))
        own = max(1, int(round((end_t - t) / (tab_obj.midi.tick_to_time(ticks_per_16th) - tab_obj.midi.tick_to_time(0))))) if end_t else 1
        L = own if nxt is None else max(1, min(own, nxt - s16))
        out.append((s16, L, sf))
    return out


def write_gp5(path, title, bpm, beats_per_bar, tuning, tracks, denominator=4):
    """tracks: [(name, events)] with events from track_events(). Time signature beats_per_bar/denominator
    (4/4, 3/4, 12/8 ...); bpm is the MIDI tempo (quarter notes)."""
    import guitarpro as gp
    bar16 = beats_per_bar * 16 // denominator
    beat16 = 6 if denominator == 8 and beats_per_bar % 3 == 0 else 16 // denominator
    last = max((s + L for _, ev in tracks for s, L, _ in ev), default=bar16)
    n_measures = max(1, -(-last // bar16))
    song = gp.Song()
    # GP5 stores text as cp1252: Korean titles are romanized, the file name keeps the original
    roman = {"흰수염고래": "Huinsuyeom Gorae", "한 페이지가 될 수 있게": "Han Page-ga Doel Su Itge"}
    for ko, en in roman.items():
        title = title.replace(ko, en)
    song.title = title.encode("cp1252", "ignore").decode("cp1252")
    song.tempo = int(round(bpm))
    h = song.measureHeaders[0]
    h.timeSignature.numerator = beats_per_bar
    h.timeSignature.denominator.value = denominator
    strings = lambda trk: [gp.GuitarString(i + 1, v) for i, v in enumerate(TUNINGS[tuning])]
    gtracks = [song.tracks[0]]
    for k in range(1, len(tracks)):
        t = gp.Track(song, number=k + 1)
        t.measures = [gp.Measure(t, hh) for hh in song.measureHeaders]
        song.tracks.append(t)
        gtracks.append(t)
    for i, (t, (name, _)) in enumerate(zip(gtracks, tracks)):
        t.name = name
        t.strings = strings(t)
        t.channel = gp.MidiChannel(channel=2 * i, effectChannel=2 * i + 1, instrument=29 if i else 30)
    for _ in range(n_measures - 1):
        song.newMeasure()
    for t in song.measureHeaders:
        t.timeSignature.numerator = beats_per_bar
        t.timeSignature.denominator.value = denominator

    for gt, (_, ev) in zip(gtracks, tracks):
        # timeline of segments over the whole song: (start16, len16, notes or None, tied)
        segs, cur = [], 0
        for s, L, sf in ev:
            if s > cur:
                segs.append((cur, s - cur, None))
            if s < cur:          # overlapping event: shorten previous
                ps, pl, pn = segs[-1]
                segs[-1] = (ps, max(1, s - ps), pn)
                if s <= ps:
                    continue
            segs.append((s, L, sf))
            cur = s + L
        if cur < n_measures * bar16:
            segs.append((cur, n_measures * bar16 - cur, None))
        # cut at barlines and into notatable lengths
        per_measure = collections.defaultdict(list)
        for s, L, sf in segs:
            first = True
            while L > 0:
                m, pos = divmod(s, bar16)
                take = min(L, bar16 - pos)
                for piece in beat_pieces(pos, take, beat16, bar16):
                    per_measure[m].append((piece, sf, not first))
                    first = False
                s += take
                L -= take
        for mi, measure in enumerate(gt.measures):
            voice = measure.voices[0]
            for (L, v, dotted), sf, tied in per_measure.get(mi, [((bar16, 1, False), None, False)]):
                beat = gp.Beat(voice, duration=gp.Duration(value=v, isDotted=dotted),
                               status=gp.BeatStatus.rest if sf is None else gp.BeatStatus.normal)
                if sf:
                    for string, fret in sf:
                        beat.notes.append(gp.Note(beat, value=fret, string=string,
                                                  type=gp.NoteType.tie if tied else gp.NoteType.normal))
                voice.beats.append(beat)
    gp.write(song, str(path))
    return n_measures


def main(src, out_dir, merged_tab=True, chord_reduction=True, split="auto", refine=True):
    """split: "auto" (decide_split), "always" (skyline lead/rhythm), "never" (one guitar part)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pm = pretty_midi.PrettyMIDI(src)
    notes = guitar_notes(pm)
    tuning = choose_tuning([n.pitch for n in notes])
    print(f"guitar notes {len(notes)} · tuning {tuning} {NAMES[tuning]}")
    write_tuning(out_dir, tuning)
    two, ds = decide_split(notes, tuning)
    do_split = two if split == "auto" else split == "always"
    print(f"split check: unplayable onsets {ds['unplayable'] * 100:.1f}% · wider than 2 octaves {ds['wide'] * 100:.1f}% "
          f"-> {'split (two guitars)' if do_split else 'one guitar'}" + ("" if split == "auto" else f" (--split {split})"))

    if chord_reduction:
        merged_notes, mst = reduce_chords(notes, tuning)
        print(f"{'merged' if do_split else 'guitar'} {len(merged_notes)} notes "
              f"(dropped {mst['notes_dropped']} of {mst['notes_in']} to make chords playable)")
    else:
        merged_notes = [pretty_midi.Note(100, fold_range(n.pitch, tuning), n.start, n.end) for n in notes]
    merged = part_midi(pm, merged_notes, "Guitar (merged)" if do_split else "Guitar")

    parts, todo = {}, []
    st = {"split": do_split, **ds}
    if do_split:
        lead, rhythm, sst = split_and_clean(notes, tuning, chord_reduction)
        st.update(sst)
        print(f"lead {sst['lead_notes']} notes · rhythm {sst['rhythm_notes']} notes "
              f"(dropped {sst['rhythm_notes_dropped']} of {sst['rhythm_notes_in']} to make chords playable)")
        both = part_midi(pm, lead, "Guitar 1 (lead)")
        r = pretty_midi.Instrument(program=29, name="Guitar 2 (rhythm)")
        r.notes = rhythm
        both.instruments.append(r)
        both.write(str(out_dir / "skyline_lead_rhythm.mid"))
        parts = {"merged": merged.instruments[0].notes, "lead": lead, "rhythm": rhythm}
        todo = [("merged", merged)] if merged_tab else []
        todo += [("lead", part_midi(pm, lead, "lead")), ("rhythm", part_midi(pm, rhythm, "rhythm"))]
    else:
        merged.write(str(out_dir / "guitar.mid"))
        parts = {"guitar": merged.instruments[0].notes}
        todo = [("guitar", merged)]

    tabs, report = {}, {}
    for name, midi in todo:
        p, t = tab(midi, f"tab_{name}", tuning, out_dir, refine=refine)
        tabs[name] = t
        n, big, med = jump_stats(p)
        report[name] = (n, big)
        print(f"  TAB {name:7s}: {n} fretted events · jumps >5 frets: {big} ({big / max(n - 1, 1) * 100:.1f}%) · median move {med:.1f} frets")

    t16 = pm.resolution // 4
    bpm = pm.get_tempo_changes()[1][0]
    ts = pm.time_signature_changes[0] if pm.time_signature_changes else None
    num, den = (ts.numerator, ts.denominator) if ts else (4, 4)
    title = Path(src).stem.replace("_aligned", "")
    ev = {k: track_events(tabs[k], parts[k], t16) for k in tabs}
    if do_split:
        write_gp5(out_dir / f"{title} - skyline lead+rhythm.gp5", title, bpm, num, tuning,
                  [("Guitar 1 (lead)", ev["lead"]), ("Guitar 2 (rhythm)", ev["rhythm"])], den)
        if merged_tab:
            write_gp5(out_dir / f"{title} - merged.gp5", title, bpm, num, tuning, [("Guitar (merged)", ev["merged"])], den)
    else:
        write_gp5(out_dir / f"{title} - guitar.gp5", title, bpm, num, tuning, [("Guitar", ev["guitar"])], den)
    return tuning, st, report


def cli(argv=None):
    p = argparse.ArgumentParser(description="Skyline lead/rhythm split + tuttut TAB + Guitar Pro export")
    p.add_argument("midi", help="beat-aligned MIDI (ml/beat_align output)")
    p.add_argument("out_dir", help="output folder")
    p.add_argument("--split", choices=["auto", "always", "never"], default="auto",
                   help="auto (default): split into lead/rhythm only when the part looks like two guitars; "
                        "always: always split; never: one guitar part")
    p.add_argument("--no-merged", action="store_true", help="skip the merged-part TAB (split songs only)")
    p.add_argument("--no-chord-reduction", action="store_true",
                   help="keep every chord note (default: max 6 notes, fretted notes within 4 frets; "
                        "without it tuttut can take over an hour on large songs)")
    p.add_argument("--no-refine", action="store_true",
                   help="keep tuttut's string/fret choice (default: move open-string and far notes to the hand)")
    a = p.parse_args(argv)
    main(a.midi, a.out_dir, merged_tab=not a.no_merged, chord_reduction=not a.no_chord_reduction, split=a.split,
         refine=not a.no_refine)


if __name__ == "__main__":
    cli()
