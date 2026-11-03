"""T6 for the guitar and bass TAB (band14): onsets one player cannot play and notes outside the range.

    python eval/t6_tab.py RESULTS_DIR      # one folder per song, with guitar/*.gp5 and bass/*.gp5 (unified.py output)

Reads every Guitar Pro track and checks each beat that starts notes against the rules skyline_tab.py
enforces: one note per string, no more notes than strings, fretted notes within MAX_SPAN (4) frets,
frets 0..NFRETS (20). Bass beats with more than one note are counted separately (bass_tab keeps one
note per onset). Prints one line per track and the totals; exits 1 if T6 fails.
The keyboard part of T6 is the piano_playable.py check (ml/guitar_tab).

Written with Claude (AI); reviewed by Soobin Jo.
"""
import collections
import sys
from pathlib import Path

import guitarpro as gp

NFRETS, MAX_SPAN = 20, 4   # ml/guitar_tab/skyline_tab.py


def check_track(track, bass=False):
    c = collections.Counter()
    nstr = len(track.strings)
    for m in track.measures:
        for v in m.voices:
            for b in v.beats:
                new = [n for n in b.notes if n.type == gp.NoteType.normal]
                if not new:
                    continue
                c["onsets"] += 1
                strings = [n.string for n in new]
                fretted = [n.value for n in new if n.value > 0]
                bad = {"same_string": len(set(strings)) < len(strings),
                       "too_many": len(new) > nstr,
                       "span": bool(fretted) and max(fretted) - min(fretted) > MAX_SPAN}
                for k, v in bad.items():
                    c[k] += v
                c["unplayable_onsets"] += any(bad.values())
                c["out_of_range_notes"] += sum(1 for n in new if not 0 <= n.value <= NFRETS)
                if bass:
                    c["bass_chords"] += len(new) > 1
    return c


def main(root):
    total = collections.Counter()
    for song in sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith("_")):
        for part in ("guitar", "bass"):
            for f in sorted((song / part).glob("*.gp5")):
                for t in gp.parse(str(f)).tracks:
                    c = check_track(t, bass=part == "bass")
                    print(f"{song.name} | {part} [{t.name}] onsets {c['onsets']} · unplayable {c['unplayable_onsets']} "
                          f"(span {c['span']}, same string {c['same_string']}, too many {c['too_many']}) · "
                          f"out of range {c['out_of_range_notes']}" + (f" · bass chords {c['bass_chords']}" if part == "bass" else ""))
                    for k, v in c.items():
                        total[f"{part}_{k}"] += v
    print("total:", dict(total))
    bad = sum(v for k, v in total.items() if k.endswith(("unplayable_onsets", "out_of_range_notes", "bass_chords")))
    print("T6 (guitar/bass):", "pass" if bad == 0 else f"fail ({bad})")
    return bad == 0


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1]) else 1)
