#!/usr/bin/env python3
"""Experiment: beat and quantization fixes for the keyboard (piano + other) part, on top of
ml/beat_align/align.py. Not part of the pipeline yet.

Beat level (before alignment)
  A. fill_half_tempo   Where Beat This! counted half notes for a while (4+ beat intervals in a row at about
                       2x the median), a beat is inserted in the middle of each such interval. Single long
                       intervals are left alone (filling one shifts every later bar, and it was as often
                       wrong as right).
  B. choose_bar_phase  align.py's bar phase (first downbeat + drum backbeat rule) is kept unless the phase
                       that puts the most Beat This! downbeats on beat 1 differs AND keyboard chords change at
                       least HARM_RATIO times as much on that phase's beat 1.

Note level
  1. fix_runs          Runs of evenly spaced keyboard chords (3+ onsets, spacing within TOL of a 16th, 8th,
                       quarter ...) are placed on the grid together (chord k at start + k * spacing). The
                       start snaps to an 8th position when the song is mostly on 8ths (EIGHTH_SHARE); when it
                       is halfway between two positions, the in-bar start that confident runs use wins.
                       A chord shared by two runs is moved once.
  2. fix_ends          After alignment, a keyboard note ending one 16th before or after the next keyboard
                       chord ends exactly at that chord.
  3. fix_chord_ends    After alignment, notes of one keyboard track that start together end together (most
                       common end, cut at the track's next onset).

Output: "<name> - 1_current.mid" (align.py as the pipeline runs it, drum sync on) and
"<name> - 6_beats+runs+ends+chords.mid" (A, B, 1, 2, 3), plus "<name> - report.json".
--all-variants also writes the note fixes one by one without A/B.

    python experiments/beat-fix/beat_fix.py --keys gated.mid --drums drums_gated.mid \
        --beats beats.json --out-dir out --name "Beautiful Things"

Inputs are the gated keyboard MIDI and drum MIDI before alignment and the Beat This! JSON
({"beats": [...], "downbeats": [...]}). Only keyboard notes are changed; drums go through align.py.

Written with Claude (AI); experiment script.
"""
import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path

import mido
import numpy as np
import pretty_midi

EIGHTH_SHARE = 0.8   # song counts as "mostly on 8ths" above this share
TOL = 0.2            # spacing tolerance (fraction of the spacing)
MIN_CHORDS = 3
MAX_MOVE = 1.5       # cells (16ths); a run that would move a chord further is left alone
AMBIGUOUS = 0.15     # start within this many steps of the halfway point counts as ambiguous
CHORD_GAP = 0.04     # seconds; onsets closer than this are one chord


def grid(align, beats, downbeats, onsets):
    """Beat times as align.py will use them (compound meters fixed) and cells per beat."""
    b = np.unique(np.asarray(beats, float))
    d = np.asarray(downbeats, float)
    found, dbpm, bb = align.detect_compound(b, onsets, d)
    if found:
        b, d = map(np.asarray, align.fix_beats(b, d, dbpm, bb))
    bpb = align.estimate_beats_per_bar(np.asarray(b), np.asarray(d))
    off = align.compute_beat_offset(np.asarray(b), np.asarray(d), bpb)
    return np.asarray(b), (6 if found else 4), bpb, off


def chords_of(midi):
    notes = sorted((n for i in midi.instruments if not i.is_drum for n in i.notes), key=lambda n: n.start)
    out = []
    for n in notes:
        if out and n.start - out[-1][0].start < CHORD_GAP:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def find_runs(p, levels):
    runs, i = [], 0
    while i < len(p) - 1:
        d = p[i + 1] - p[i]
        v = min(levels, key=lambda L: abs(d - L))
        if abs(d - v) > TOL * v:
            i += 1
            continue
        j = i + 1
        while j + 1 < len(p) and abs((p[j + 1] - p[j]) - v) <= TOL * v:
            j += 1
        if j - i + 1 >= MIN_CHORDS:
            runs.append((i, j, v))
            i = j
        else:
            i += 1
    return runs


def fix_runs(midi, beats, sub, bpb, off):
    """Fix 1, in place. Returns stats."""
    idx = np.arange(len(beats))
    to_cell = lambda t: (np.interp(t, beats, idx) + off) * sub
    to_time = lambda c: np.interp(c / sub - off, idx, beats)
    ch = chords_of(midi)
    if len(ch) < MIN_CHORDS:
        return {"runs": 0, "moved_chords": 0}
    t = np.array([np.median([n.start for n in c]) for c in ch])
    p = to_cell(t)
    eighth_share = float(np.mean(np.round(p) % 2 == 0))
    mostly_8ths = eighth_share >= EIGHTH_SHARE
    levels = [1, 2, 4] if sub == 4 else [1, 2, 3, 6]
    bar = bpb * sub
    plans, starts = [], Counter()
    for i, j, v in find_runs(p, levels):
        k = np.arange(j - i + 1)
        step = v if (v == 2 and mostly_8ths) or v == sub else 1
        c_raw = np.mean(p[i:j + 1] - v * k) / step
        frac = c_raw - np.floor(c_raw)
        ambiguous = abs(frac - 0.5) < AMBIGUOUS
        cands = [np.floor(c_raw) * step, np.ceil(c_raw) * step] if ambiguous else [round(c_raw) * step]
        plans.append((i, j, v, k, cands))
        if not ambiguous:
            starts[(v, int(cands[0] % bar))] += 1
    moved = runs = amb = 0
    target = {}   # chord index -> grid cell; a chord shared by two runs keeps the first run's position
    for i, j, v, k, cands in plans:
        if len(cands) == 2:   # pick the in-bar start position confident runs use most
            amb += 1
            cands = [max(cands, key=lambda c: (starts[(v, int(c % bar))], -abs(c - (np.mean(p[i:j + 1] - v * k)))))]
        q = cands[0] + v * k
        if np.max(np.abs(q - p[i:j + 1])) > MAX_MOVE:
            continue
        runs += 1
        for kk in k:
            target.setdefault(i + int(kk), q[kk])
    for ci, cell in target.items():
        delta = float(to_time(cell)) - t[ci]
        if abs(delta) > 0.005:
            moved += 1
        for n in ch[ci]:
            n.start += delta
            n.end += delta
    return {"eighth_share": round(eighth_share, 3), "mostly_8ths": mostly_8ths, "runs": runs,
            "ambiguous_runs": amb, "moved_chords": moved, "chords": len(ch)}


def fix_ends(path_in, path_out):
    """Fix 2 on an aligned MIDI file (ticks on a 16th grid). Returns number of notes changed."""
    mf = mido.MidiFile(path_in)
    cell = mf.ticks_per_beat // 4
    tracks = []
    for tr in mf.tracks:
        drum = any(m.type == "note_on" and m.channel == 9 for m in tr)
        t, ev = 0, []
        for m in tr:
            t += m.time
            ev.append((t, m))
        tracks.append((drum, ev))
    onsets = sorted({t for drum, ev in tracks if not drum for t, m in ev if m.type == "note_on" and m.velocity > 0})
    on = np.asarray(onsets)
    changed = 0
    new_tracks = []
    for drum, ev in tracks:
        if drum:
            new_tracks.append(ev)
            continue
        out, open_ = [], {}
        for t, m in ev:
            if m.type == "note_on" and m.velocity > 0:
                open_[(m.channel, m.note)] = t
            elif m.type in ("note_off", "note_on") and (m.channel, m.note) in open_:
                s = open_.pop((m.channel, m.note))
                k = np.searchsorted(on, s, side="right")
                if k < len(on) and abs(on[k] - t) == cell and on[k] > s:
                    t = int(on[k])
                    changed += 1
            out.append((t, m))
        out.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" or (x[1].type == "note_on" and x[1].velocity == 0) else 1))
        new_tracks.append(out)
    res = mido.MidiFile(ticks_per_beat=mf.ticks_per_beat, type=mf.type)
    for ev in new_tracks:
        tr, prev = mido.MidiTrack(), 0
        for t, m in ev:
            tr.append(m.copy(time=t - prev))
            prev = t
        res.tracks.append(tr)
    res.save(path_out)
    return changed


def _notes_by_track(mf):
    """[(is_drum, [[start, end, channel, pitch, velocity], ...])] in ticks."""
    out = []
    for tr in mf.tracks:
        drum = any(m.type == "note_on" and m.channel == 9 for m in tr)
        t, open_, notes, meta = 0, {}, [], []
        for m in tr:
            t += m.time
            if m.type == "note_on" and m.velocity > 0:
                if (m.channel, m.note) in open_:   # re-struck while still sounding: close the old one here
                    s, v = open_.pop((m.channel, m.note))
                    if t > s:
                        notes.append([s, t, m.channel, m.note, v])
                open_[(m.channel, m.note)] = (t, m.velocity)
            elif m.type in ("note_off", "note_on"):
                if (m.channel, m.note) in open_:
                    s, v = open_.pop((m.channel, m.note))
                    notes.append([s, t, m.channel, m.note, v])
            else:
                meta.append((t, m))
        out.append((drum, notes, meta))
    return out


def _write(mf, tracks, path):
    res = mido.MidiFile(ticks_per_beat=mf.ticks_per_beat, type=mf.type)
    for drum, notes, meta in tracks:
        ev = [(t, 0, m) for t, m in meta if m.type != "end_of_track"]
        for s, e, ch, p, v in notes:
            ev.append((e, 1, mido.Message("note_off", channel=ch, note=p, velocity=0)))
            ev.append((s, 2, mido.Message("note_on", channel=ch, note=p, velocity=v)))
        ev.sort(key=lambda x: (x[0], x[1]))
        tr, prev = mido.MidiTrack(), 0
        for t, _, m in ev:
            tr.append(m.copy(time=t - prev))
            prev = t
        tr.append(mido.MetaMessage("end_of_track", time=0))
        res.tracks.append(tr)
    res.save(path)


def fix_chord_ends(path_in, path_out):
    """Fix 3 on an aligned MIDI file: in each keyboard track, notes that start together end together
    (at the most common end among them; ties -> the earlier end), and no earlier than one 16th after the
    start and no later than the track's next onset. Returns number of notes changed."""
    mf = mido.MidiFile(path_in)
    cell = mf.ticks_per_beat // 4
    tracks = _notes_by_track(mf)
    changed = 0
    for drum, notes, _ in tracks:
        if drum or not notes:
            continue
        groups = {}
        for n in notes:
            groups.setdefault(n[0], []).append(n)
        onsets = np.array(sorted(groups))
        for s, grp in groups.items():
            cnt = Counter(n[1] for n in grp)
            end = min(cnt, key=lambda e: (-cnt[e], e))
            k = np.searchsorted(onsets, s, side="right")
            if k < len(onsets):
                end = min(end, int(onsets[k]))
            end = max(end, s + cell)
            for n in grp:
                if n[1] != end:
                    n[1] = end
                    changed += 1
    _write(mf, tracks, path_out)
    return changed


HALF_MIN_RUN = 4   # ~2x beat intervals in a row before a section counts as tracked at half tempo


def fill_half_tempo(beats, lo=1.7, hi=2.3, min_run=HALF_MIN_RUN):
    """Fix A: insert a midpoint beat into every ~2x interval inside runs of >= min_run such intervals
    (Beat This! counting half notes for a while). Single long intervals are left alone: filling one
    shifts every later bar, and it was as often wrong as right. Returns (beats, added)."""
    B = np.asarray(beats, float)
    iv = np.diff(B)
    med = np.median(iv)
    dbl = (iv > lo * med) & (iv < hi * med)
    fill = np.zeros(len(iv), bool)
    k = 0
    while k < len(iv):
        if not dbl[k]:
            k += 1
            continue
        j = k
        while j + 1 < len(iv) and dbl[j + 1]:
            j += 1
        if j - k + 1 >= min_run:
            fill[k:j + 1] = True
        k = j + 1
    out = [B[0]]
    for x, v in enumerate(iv):
        if fill[x]:
            out.append(B[x] + v / 2)
        out.append(B[x + 1])
    return np.array(out), int(fill.sum())


def downbeat_agreement(beats, downbeats, bpb, offset):
    """Share of Beat This! downbeats that land on beat 1 of a written bar."""
    idx = np.arange(len(beats))
    D = np.asarray(downbeats, float)
    D = D[(D > beats[0]) & (D < beats[-1])]
    if len(D) == 0:
        return float("nan"), []
    raw = np.array([int(round(np.interp(x, beats, idx))) for x in D])
    return float(np.mean((raw + offset) % bpb == 0)), raw


def majority_offset(beats, downbeats, bpb):
    """Fix B: bar phase that puts the most Beat This! downbeats on beat 1 (instead of the first one only)."""
    _, raw = downbeat_agreement(beats, downbeats, bpb, 0)
    if len(raw) == 0:
        return 0
    return max(range(bpb), key=lambda o: np.mean((raw + o) % bpb == 0))


HARM_RATIO = 1.5   # majority phase must have this much more chord change on its beat 1 to override


def harmonic_change(midi, beats, bpb):
    """Share of keyboard chord change (cosine distance between pitch-class content of consecutive beats)
    entering each beat residue k % bpb (k = beat index). Chords change most on beat 1."""
    idx = np.arange(len(beats))
    n = len(beats)
    C = np.zeros((n, 12))
    for inst in midi.instruments:
        if inst.is_drum:
            continue
        for note in inst.notes:
            a, e = np.interp(note.start, beats, idx), np.interp(note.end, beats, idx)
            for k in range(int(np.floor(a)), int(np.ceil(e))):
                if 0 <= k < n:
                    w = min(e, k + 1) - max(a, k)
                    if w > 0:
                        C[k, note.pitch % 12] += w
    nrm = np.linalg.norm(C, axis=1) + 1e-9
    Cn = C / nrm[:, None]
    d = 1 - np.sum(Cn[1:] * Cn[:-1], axis=1)
    active = (nrm[1:] > 0.5) & (nrm[:-1] > 0.5)
    sc = np.zeros(bpb)
    for k in range(1, n):
        if active[k - 1]:
            sc[k % bpb] += d[k - 1]
    return sc / sc.sum() if sc.sum() else sc


def choose_bar_phase(midi, beats, sub, downbeats, bpb, drum_offset):
    """Fix B (conditional): keep align.py's phase (first downbeat + drum backbeat rule) unless the phase that
    puts the most Beat This! downbeats on beat 1 differs AND keyboard chords change clearly more on that
    phase's beat 1 (HARM_RATIO). Beat This! can put downbeats half a bar late for a whole song, and
    kick 1+3 / snare 2+4 cannot tell half-bar shifts apart, so the downbeat majority alone is not enough."""
    maj = majority_offset(beats, downbeats, bpb)
    info = {"drum_rule_phase": int(drum_offset), "majority_phase": int(maj)}
    if maj == drum_offset or sub != 4:
        return int(drum_offset), info
    h = harmonic_change(midi, beats, bpb)
    score = lambda o: float(h[(-o) % bpb])
    info["chord_change_on_beat1"] = {"drum_rule": round(score(drum_offset), 3), "majority": round(score(maj), 3)}
    use = score(maj) >= HARM_RATIO * score(drum_offset)
    return (int(maj) if use else int(drum_offset)), info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keys", required=True, help="keyboard MIDI before alignment (gated.mid)")
    ap.add_argument("--drums", help="drum MIDI before alignment (drums_gated.mid); enables drum sync")
    ap.add_argument("--beats", required=True, help="Beat This! JSON with beats and downbeats")
    ap.add_argument("--align-dir", default=str(Path(__file__).resolve().parents[2] / "ml" / "beat_align"),
                    help="folder with align.py and drum_sync.py (default: ml/beat_align of this repository)")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--name", default="song")
    ap.add_argument("--all-variants", action="store_true",
                    help="also write the in-between versions (default: only 1_current and 6_beats+runs+ends+chords)")
    a = ap.parse_args()
    sys.path.insert(0, a.align_dir)
    import align

    b = json.load(open(a.beats))
    base = pretty_midi.PrettyMIDI(a.keys)
    if a.drums:
        base.instruments += pretty_midi.PrettyMIDI(a.drums).instruments
    beats, sub, bpb, off = grid(align, b["beats"], b["downbeats"], [n.start for i in base.instruments for n in i.notes])
    a.out_dir.mkdir(parents=True, exist_ok=True)
    tmp = a.out_dir / "_tmp"
    tmp.mkdir(exist_ok=True)
    report = {}

    def aligned(midi, tag):
        src, dst = tmp / f"{tag}_in.mid", tmp / f"{tag}_aligned.mid"
        midi.write(str(src))
        align.align_midi(str(src), str(dst), beats=b["beats"], downbeats=b["downbeats"], drum_sync=bool(a.drums))
        return dst

    cur = aligned(copy.deepcopy(base), "current")
    runs_midi = copy.deepcopy(base)
    report["runs"] = fix_runs(runs_midi, beats, sub, bpb, off)
    run = aligned(runs_midi, "runs")
    outs = {
        "1_current": cur,
        "2_runs": run,
    }
    report["ends_only"] = fix_ends(str(cur), str(tmp / "ends.mid"))
    report["runs_and_ends"] = fix_ends(str(run), str(tmp / "runs_ends.mid"))
    outs["3_ends"] = tmp / "ends.mid"
    outs["4_runs+ends"] = tmp / "runs_ends.mid"
    report["chords_only"] = fix_chord_ends(str(cur), str(tmp / "chords.mid"))
    report["runs_ends_chords"] = fix_chord_ends(str(tmp / "runs_ends.mid"), str(tmp / "all.mid"))
    outs["5_chords"] = tmp / "chords.mid"
    outs["5b_runs+ends+chords_no_beat_fix"] = tmp / "all.mid"
    # fixed beats (fix A + conditional fix B) under the three note fixes: "6_beats+runs+ends+chords"
    onsets = [n.start for i in base.instruments for n in i.notes]
    r0 = align.align_midi(str(tmp / "current_in.mid"), str(tmp / "_probe0.mid"), beats=b["beats"],
                          downbeats=b["downbeats"], drum_sync=bool(a.drums))
    nb, added = fill_half_tempo(b["beats"])
    r_nb = align.align_midi(str(tmp / "current_in.mid"), str(tmp / "_probe1.mid"), beats=list(nb),
                            downbeats=b["downbeats"], drum_sync=bool(a.drums))
    g_beats, g_sub, g_bpb, g_detected = grid(align, nb, b["downbeats"], onsets)
    phase, info = choose_bar_phase(base, g_beats, g_sub, b["downbeats"], g_bpb, r_nb.beat_offset)
    shift = (g_detected - phase) % g_bpb
    shift = shift - g_bpb if shift > g_bpb // 2 else shift
    fixed_midi = copy.deepcopy(base)
    report["beats_fix"] = {
        "beats_added": added, "beats_per_bar": int(g_bpb), "bar_phase": phase, **info,
        "downbeat_on_barline_before": round(downbeat_agreement(beats, b["downbeats"], bpb, r0.beat_offset)[0], 3),
        "downbeat_on_barline_after": round(downbeat_agreement(g_beats, b["downbeats"], g_bpb, phase)[0], 3),
        "runs": fix_runs(fixed_midi, g_beats, g_sub, g_bpb, phase)}
    src, dst = tmp / "beats_in.mid", tmp / "beats_aligned.mid"
    fixed_midi.write(str(src))
    r1 = align.align_midi(str(src), str(dst), beats=list(nb), downbeats=b["downbeats"], drum_sync=bool(a.drums),
                          downbeat_shift=shift)
    if r1.beat_offset != phase:
        raise RuntimeError(f"bar phase {r1.beat_offset} != intended {phase}")
    report["beats_fix"]["ends"] = fix_ends(str(dst), str(tmp / "beats_ends.mid"))
    report["beats_fix"]["chords"] = fix_chord_ends(str(tmp / "beats_ends.mid"), str(tmp / "beats_all.mid"))
    outs["6_beats+runs+ends+chords"] = tmp / "beats_all.mid"
    if not a.all_variants:
        outs = {k: v for k, v in outs.items() if k in ("1_current", "6_beats+runs+ends+chords")}
    for k, p in outs.items():
        Path(a.out_dir / f"{a.name} - {k}.mid").write_bytes(Path(p).read_bytes())
    json.dump(report, open(a.out_dir / f"{a.name} - report.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
