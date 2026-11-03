"""Four-instrument scores (T1'-T3'): rescore the eval_sep.py outputs on keyboard, guitar, bass and drum notes only.

Run with /data/envs/mus/bin/python after eval_sep.py (no separation or transcription is repeated):

    python rescore4.py SONGS.txt            # -> /data/rwc/results/summary4.csv

Why: the RWC reference has every part of the song (vocal melody, strings, brass, synths), but the separated
pipeline transcribes only the drums, bass, guitar and piano stems, so the original scores count parts it never
tries to transcribe as missed notes, while the no-separation baseline can still get credit for them.

Reference: tracks are kept by GM program family (keys 0-7 and 16-23, guitar 24-31, bass 32-39, drums),
with two corrections found by listing the 12 reference files:
  - a track named exactly MELODY / MELO / MELODY 1 / VOCAL is the vocal melody and is dropped whatever its
    program (RWC_P047 'MELODY' is GM 22, in the keyboard range); 'GT MELO 1' etc. are guitar and stay,
  - RWC_P063 'E.PIANO' (GM 99) is a keyboard part and is kept as keys (written as GM 4, electric piano).
Estimate: separated runs keep every note (all come from the four stems, family from the stem, as in
eval_sep.py); the no-separation baseline keeps notes whose program is in the four families.
The filtered MIDIs are scored with the same metrics.score and per-family onset F1 as eval_sep.py.

Written with Claude (AI); experiment script for the separation comparison, not part of the app pipeline.
"""
import copy
import csv
import json
import sys
from pathlib import Path

import pretty_midi

import eval_sep
from eval_sep import FAMILIES, ROOT, family_of_program

VOCAL_NAMES = {"MELODY", "MELO", "MELODY 1", "VOCAL"}
KEYS_OVERRIDE = {("RWC_P063", "E.PIANO"): 4}   # (song, track name) -> GM program used for the keyboard part


def ref_family(song, inst):
    """Family of a reference track for the four-instrument scores (None: dropped)."""
    name = inst.name.strip().upper()
    if not inst.is_drum and name in VOCAL_NAMES:
        return None
    if (song, inst.name.strip()) in KEYS_OVERRIDE:
        return "keys"
    return family_of_program(inst)


def filtered(pm, keep):
    """Copy of pm with the instruments for which keep(index, inst) returns a GM program (or True: unchanged)."""
    out = pretty_midi.PrettyMIDI(resolution=pm.resolution)
    for k, inst in enumerate(pm.instruments):
        p = keep(k, inst)
        if p is None or p is False:
            continue
        inst = copy.deepcopy(inst)
        if p is not True:
            inst.program = int(p)
        out.instruments.append(inst)
    return out


def rescore(song, method):
    d = ROOT / "results" / method / song
    est_path = ROOT / "base" / song / "muscriptor.mid" if method == "none" else d / "merged.mid"
    if not est_path.exists():
        return None
    ref = pretty_midi.PrettyMIDI(str(ROOT / "refs" / "RWC-P" / f"{song}.mid"))
    ref4 = filtered(ref, lambda k, i: None if ref_family(song, i) is None
                    else KEYS_OVERRIDE.get((song, i.name.strip()), True))
    est = pretty_midi.PrettyMIDI(str(est_path))
    if method == "none":
        by_stem = None
        est4 = filtered(est, lambda k, i: family_of_program(i) is not None)
    else:
        by_stem = json.load(open(d / "merged_stems.json"))
        est4 = est
    d4 = ROOT / "results4" / method / song
    d4.mkdir(parents=True, exist_ok=True)
    ref4.write(str(d4 / "ref4.mid"))
    est4.write(str(d4 / "est4.mid"))
    s = eval_sep.score_song(d4 / "ref4.mid", d4 / "est4.mid", by_stem)
    s["kept_notes"] = {"reference": sum(len(i.notes) for i in ref4.instruments),
                       "reference_all": sum(len(i.notes) for i in ref.instruments),
                       "estimate": sum(len(i.notes) for i in est4.instruments),
                       "estimate_all": sum(len(i.notes) for i in est.instruments)}
    json.dump(s, open(d4 / "scores.json", "w"), indent=1)
    return s


def main():
    songs = [s.strip() for s in open(sys.argv[1]) if s.strip()]
    rows = []
    for song in songs:
        for method in ("none",) + eval_sep.METHODS:
            s = rescore(song, method)
            if s is None:
                print(f"{song} {method}: no output yet")
                continue
            row = {"song": song, "method": method}
            for k in ("onset", "offset", "frame", "drums", "multi"):
                row[k] = round(s[k]["f1"], 4)
            for f in FAMILIES:
                v = s["family_onset"][f]["f1"]
                row[f"{f}_onset"] = "" if v is None else round(v, 4)
            row.update({f"notes_{k}": v for k, v in s["kept_notes"].items()})
            rows.append(row)
            print(f"{song} {method}: multi4 F1 {row['multi']:.4f}, onset4 F1 {row['onset']:.4f}")
    if rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(ROOT / "results" / "summary4.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, keys)
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} rows -> {ROOT / 'results' / 'summary4.csv'}")


if __name__ == "__main__":
    main()
