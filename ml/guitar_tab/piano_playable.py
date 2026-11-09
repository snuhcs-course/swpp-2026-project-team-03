"""Keyboard part -> something two hands can play (rule-based, like the guitar chord reduction).

MuScriptor can write a held keyboard chord (a synth pad, a sustained piano chord) as the same chord
struck again on every 16th note, and can stack 9-10 notes over three octaves in one chord. Neither can
be played. Two rules, on the beat-aligned MIDI (notes on a 16th grid):

1. Re-attack merge: when one pitch is struck again and again on consecutive 16ths (at least
   MERGE_MIN_RUN notes, at most one 16th missing in a row, mostly 1/16 apart), the run becomes one
   held note. Repeated 8ths (every step 2/16) are left alone.
2. Hand limits per onset: the right hand takes the top note and everything within HAND_SPAN
   semitones below it, the left hand the bottom note and everything within HAND_SPAN above it
   (notes in neither hand are dropped). Each hand keeps at most HAND_NOTES notes: its outer note
   always, then the others, dropping octave doublings first, then inner notes.

All keyboard tracks are treated as one player (the piano stem may be split into piano / electric piano /
organ labels); a pitch struck in two of them at once is kept once. Only notes that start together are
checked; notes still held from earlier onsets are not counted, so a held chord under a fast run in the
same hands can remain.

    python piano_playable.py song_aligned.mid out.mid       # every keyboard track (GM 0-7, 16-23)

Written with Claude (AI); reviewed by Soobin Jo.
"""
import argparse
import collections
import copy

import pretty_midi

HAND_SPAN = 14        # a major 9th: comfortable reach of one hand
HAND_NOTES = 5        # fingers per hand
MERGE_MIN_RUN = 6     # repeated 16ths of one pitch before they count as one held note


def is_keyboard(inst):
    return not inst.is_drum and (0 <= inst.program <= 7 or 16 <= inst.program <= 23)


def sixteenth(pm):
    return 60.0 / pm.get_tempo_changes()[1][0] / 4


def merge_reattacks(notes, s16, min_run=MERGE_MIN_RUN):
    """Merge runs of one pitch struck on (nearly) every 16th into one held note. Returns (notes, merged)."""
    by_pitch = collections.defaultdict(list)
    for n in notes:
        by_pitch[n.pitch].append(n)
    out, merged = [], 0
    for pitch, ns in by_pitch.items():
        ns.sort(key=lambda n: n.start)
        k = [int(round(n.start / s16)) for n in ns]
        i = 0
        while i < len(ns):
            j = i
            while j + 1 < len(ns) and k[j + 1] - k[j] in (1, 2) and ns[j].end >= ns[j + 1].start - s16 - 1e-6:
                j += 1
            steps = [k[x + 1] - k[x] for x in range(i, j)]
            if j - i + 1 >= min_run and steps.count(1) * 3 >= len(steps) * 2:
                first = copy.deepcopy(ns[i])
                first.end = max(n.end for n in ns[i:j + 1])
                first.velocity = max(n.velocity for n in ns[i:j + 1])
                out.append(first)
                merged += j - i
            else:
                out += ns[i:j + 1]
            i = j + 1
    out.sort(key=lambda n: (n.start, n.pitch))
    return out, merged


def _keep(hand, outer, limit):
    """At most `limit` pitches of one hand: the outer note first, then the rest, octave doublings last."""
    if len(hand) <= limit:
        return hand
    rest = [p for p in hand if p != outer]
    seen = {outer % 12}
    first, doubled = [], []
    for p in sorted(rest, key=lambda p: abs(p - outer)):     # nearest to the outer note first
        (doubled if p % 12 in seen else first).append(p)
        seen.add(p % 12)
    return sorted([outer] + (first + doubled)[:limit - 1])


def hand_limit(pitches, span=HAND_SPAN, per_hand=HAND_NOTES):
    """Pitches two hands can play together from one onset (sorted)."""
    ps = sorted(set(pitches))
    if not ps:
        return []
    top, bottom = ps[-1], ps[0]
    right = [p for p in ps if p >= top - span]
    left = [p for p in ps if p <= bottom + span and p not in right]
    return sorted(_keep(left, bottom, per_hand) + _keep(right, top, per_hand)) if left else _keep(right, top, per_hand)


def playable(tracks, s16):
    """Apply both rules to keyboard tracks played by one player (e.g. the piano stem's piano /
    electric piano / organ labels). Re-attacks are merged per track; the hand limits look at all
    tracks together, and a pitch struck in two tracks at once is kept only in one (the louder).
    `tracks`: list of note lists. Returns (list of note lists, stats)."""
    merged = 0
    tagged = []
    for t, notes in enumerate(tracks):
        notes, m = merge_reattacks(notes, s16)
        merged += m
        tagged += [(t, n) for n in notes]
    groups = collections.OrderedDict()
    for t, n in sorted(tagged, key=lambda x: x[1].start):
        groups.setdefault(int(round(n.start / s16)), []).append((t, n))
    out = [[] for _ in tracks]
    doubled = cut = 0
    for grp in groups.values():
        keep = set(hand_limit([n.pitch for _, n in grp]))
        seen = set()
        for t, n in sorted(grp, key=lambda x: -x[1].velocity):
            if n.pitch in seen:
                doubled += 1
            elif n.pitch not in keep:
                cut += 1
            else:
                out[t].append(n)
                seen.add(n.pitch)
    for notes in out:
        notes.sort(key=lambda n: (n.start, n.pitch))
    return out, {"reattacks_merged": merged, "same_pitch_doubles": doubled, "hand_limit_dropped": cut}


def process(pm):
    """Copy of `pm` with its keyboard tracks (GM 0-7, 16-23, treated as one player) made playable.
    Returns (PrettyMIDI, stats)."""
    out = copy.deepcopy(pm)
    keys = [i for i in out.instruments if is_keyboard(i)]
    if not keys:
        return out, {"notes_in": 0, "reattacks_merged": 0, "same_pitch_doubles": 0, "hand_limit_dropped": 0}
    n0 = sum(len(i.notes) for i in keys)
    new, st = playable([i.notes for i in keys], sixteenth(pm))
    for inst, notes in zip(keys, new):
        inst.notes = notes
    return out, {"notes_in": n0, **st}


def cli(argv=None):
    p = argparse.ArgumentParser(description="Make keyboard tracks playable by two hands")
    p.add_argument("midi", help="beat-aligned MIDI")
    p.add_argument("out", help="output MIDI")
    a = p.parse_args(argv)
    pm, stats = process(pretty_midi.PrettyMIDI(a.midi))
    pm.write(a.out)
    print(stats)


if __name__ == "__main__":
    cli()
