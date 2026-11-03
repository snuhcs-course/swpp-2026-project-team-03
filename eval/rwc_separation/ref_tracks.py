"""Print every track of the RWC reference MIDIs: program, family, name, note count. Reads refs only.

    python ref_tracks.py SONGS.txt

Written with Claude (AI); used to define the four-instrument scores (T1'-T3') in eval/README.md.
"""
import sys
from pathlib import Path
import pretty_midi

def fam(i):
    if i.is_drum: return "drums"
    p = i.program
    if p <= 7 or 16 <= p <= 23: return "keys"
    if 24 <= p <= 31: return "guitar"
    if 32 <= p <= 39: return "bass"
    return "-"

for song in [s.strip() for s in open(sys.argv[1]) if s.strip()]:
    pm = pretty_midi.PrettyMIDI(f"/data/rwc/refs/RWC-P/{song}.mid")
    print(song)
    for i in pm.instruments:
        print(f"  {fam(i):6} prog {i.program:3} drum={int(i.is_drum)} notes {len(i.notes):5}  {i.name!r}")
