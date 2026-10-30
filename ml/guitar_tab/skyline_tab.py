"""Skyline baseline for guitar TAB.

MuScriptor often merges two guitars into one part. This script
1. picks a tuning (standard / half step down / drop D) from the lowest notes,
2. decides whether the part holds two guitars (auto mode, `decide_split`) and, if so, splits it with the
   skyline rule: the highest note at each onset -> lead, the rest -> rhythm; otherwise keeps one guitar part,
3. makes chords playable (max 6 notes, fretted notes within 4 frets) in the rhythm part and
   the merged part, by default; --no-chord-reduction turns this off,
4. chooses string/fret with tuttut (Viterbi over fingerings, b=0.1),
5. writes MIDI, text TAB and Guitar Pro (.gp5) files, and reports fret jumps > 5.

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
SPLIT_MIN_UNPLAYABLE = 0.05   # auto split: >= 5% of onsets cannot be fingered as one chord ...
SPLIT_MIN_WIDE = 0.06         # ... and >= 6% of onsets span more than two octaves (two guitars in two registers)
WIDE_SPAN = 24                # two octaves: E2 (6th string open) to E4 (1st string open)
TB_WEIGHTS = dict(b=0.1, height=1, length=1, n_changed_strings=1)


def guitar_notes(pm):
    gs = [i for i in pm.instruments if 24 <= i.program <= 31 and not i.is_drum]
    return sorted((n for i in gs for n in i.notes), key=lambda n: (n.start, n.pitch))


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
    fixes it). Calibrated on 11 songs (2026-10-30): two different guitars -> wide >= 8.3%, one guitar -> <= 4.2%.
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


def tab(midi, name, tuning, out_dir):
    from tuttut.logic.tab import Tab
    from tuttut.logic.theory import Tuning
    t = Tab(name, Tuning(NAMES[tuning]), midi, output_dir=str(out_dir), weights=TB_WEIGHTS)
    t.to_ascii()
    return (Path(out_dir) / name).with_suffix(".txt"), t


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
                for piece in split_len(take):
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


def main(src, out_dir, merged_tab=True, chord_reduction=True, split="auto"):
    """split: "auto" (decide_split), "always" (skyline lead/rhythm), "never" (one guitar part)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pm = pretty_midi.PrettyMIDI(src)
    notes = guitar_notes(pm)
    tuning = choose_tuning([n.pitch for n in notes])
    print(f"guitar notes {len(notes)} · tuning {tuning} {NAMES[tuning]}")
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
        p, t = tab(midi, f"tab_{name}", tuning, out_dir)
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
    a = p.parse_args(argv)
    main(a.midi, a.out_dir, merged_tab=not a.no_merged, chord_reduction=not a.no_chord_reduction, split=a.split)


if __name__ == "__main__":
    cli()
