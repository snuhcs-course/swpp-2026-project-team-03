"""RWC separation comparison: no separation vs Demucs 6-stem vs BS-RoFormer 6-stem, scored against RWC aligned MIDI.

Run with /data/envs/mus/bin/python in the GPU pod:

    python eval_sep.py SONGS.txt            # SONGS.txt: one RWC id per line, e.g. RWC_P009

For each song and each separator (demucs, bsrofo):
  1. the original mix is read from the official RWC 2.0 ZIP on Zenodo (cached in /data/rwc/audio),
  2. sep.py writes six stems (separate Python env),
  3. MuScriptor large transcribes drums/bass/guitar/piano stems with the app pipeline's instrument hints
     and decoding settings (ml/pipeline/transcribe_with_progress.py), model loaded once,
  4. the four stem MIDIs are merged (before beat alignment) and scored with /data/rwc/metrics.py
     (the team's RWC evaluation: MuScriptor paper metrics), plus onset F1 per instrument family.
"No separation" is the team's earlier MuScriptor-on-the-mix result (/data/rwc/base/<id>/muscriptor.mid),
scored the same way.  Results: /data/rwc/results/<method>/<id>/ and /data/rwc/results/summary.csv.
Finished songs are skipped on a rerun.

Written with Claude (AI); experiment script for the separation comparison, not part of the app pipeline.
"""
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi

ROOT = Path("/data/rwc")
sys.path.insert(0, str(ROOT))
import metrics  # noqa: E402  (team RWC evaluation, copied from /data/rwc-eval)

MODEL = "/data/models/muscriptor/model.safetensors"
SEP_PY = "/data/envs/sep/bin/python"
ZIP_URL = "https://zenodo.org/records/18656623/files/RWC-{}.zip?download=1"
METHODS = ("demucs", "bsrofo")
HINTS = {   # same as ml/pipeline/unified.py
    "drums": ["drums"],
    "bass": ["acoustic_bass", "electric_bass"],
    "guitar": ["acoustic_guitar", "clean_electric_guitar", "distorted_electric_guitar"],
    "piano": ["acoustic_piano", "electric_piano", "organ"],
}
FAMILIES = ("keys", "guitar", "bass", "drums")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def fetch(song):
    path = ROOT / "audio" / f"{song}.wav"
    if path.exists():
        return path
    from remotezip import RemoteZip
    path.parent.mkdir(parents=True, exist_ok=True)
    letter = song.split("_")[1][0]
    for attempt in range(1, 5):
        try:
            with RemoteZip(ZIP_URL.format(letter), timeout=180) as z:
                member = [n for n in z.namelist() if Path(n).name == f"{song}.wav"]
                data = z.read(member[0])
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.rename(path)
            return path
        except Exception as e:  # noqa: BLE001
            log(f"{song}: download retry {attempt} ({type(e).__name__})")
            time.sleep(30 * attempt)
    raise RuntimeError(f"{song}: download failed")


def family_of_program(inst):
    if inst.is_drum:
        return "drums"
    p = inst.program
    if 0 <= p <= 7 or 16 <= p <= 23:
        return "keys"
    if 24 <= p <= 31:
        return "guitar"
    if 32 <= p <= 39:
        return "bass"
    return None


def family_notes(pm, by_stem=None):
    """{family: [(start, end, pitch)]}; by_stem maps instrument index -> stem family (separated runs)."""
    out = {f: [] for f in FAMILIES}
    for k, inst in enumerate(pm.instruments):
        fam = by_stem[k] if by_stem is not None else family_of_program(inst)
        if fam:
            out[fam] += [(n.start, n.end, n.pitch) for n in inst.notes if n.end > n.start >= 0]
    return out


def onset_f1(ref, est):
    if not ref or not est:
        return {"reference": len(ref), "estimated": len(est), "f1": 0.0 if (ref or est) else None}
    ri = np.asarray([(a, b) for a, b, _ in ref]); ei = np.asarray([(a, b) for a, b, _ in est])
    rp = np.asarray([pretty_midi.note_number_to_hz(p) for *_, p in ref])
    ep = np.asarray([pretty_midi.note_number_to_hz(p) for *_, p in est])
    m = len(mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=0.05, offset_ratio=None))
    return {"reference": len(ref), "estimated": len(est), "matches": m,
            "f1": 2 * m / (len(ref) + len(est))}


def score_song(ref_path, est_path, by_stem=None):
    s = metrics.score(ref_path, est_path)
    ref_f = family_notes(pretty_midi.PrettyMIDI(str(ref_path)))
    est_f = family_notes(pretty_midi.PrettyMIDI(str(est_path)), by_stem)
    s["family_onset"] = {f: onset_f1(ref_f[f], est_f[f]) for f in FAMILIES}
    return s


def transcribe(model, wav, hints):
    from muscriptor.utils.midi import ExportOptions
    events = list(model.transcribe(str(wav), use_sampling=False, temperature=1.0, cfg_coef=1.0,
                                   instruments=hints, batch_size=None, no_eos_is_ok=True,
                                   beam_size=1, prelude_forcing=True))
    return model.events_to_midi_bytes(iter(events), beat_grid=None, export=ExportOptions())


def run_method(model, song, method, ref):
    d = ROOT / "results" / method / song
    if (d / "scores.json").exists():
        log(f"{song} {method}: done already")
        return
    d.mkdir(parents=True, exist_ok=True)
    wav = fetch(song)
    stems = d / "stems"
    t0 = time.time()
    subprocess.run([SEP_PY, str(ROOT / "sep.py"), method, str(wav), str(stems)], check=True)
    t_sep = time.time() - t0
    merged, by_stem = pretty_midi.PrettyMIDI(), []
    t1 = time.time()
    for stem, hints in HINTS.items():
        mid = d / f"{stem}.mid"
        if not mid.exists():
            mid.write_bytes(transcribe(model, stems / f"{stem}.wav", hints))
        for inst in pretty_midi.PrettyMIDI(str(mid)).instruments:
            inst.name = f"{stem}: {inst.name}"
            merged.instruments.append(inst)
            by_stem.append("keys" if stem == "piano" else stem)
    t_tr = time.time() - t1
    merged.write(str(d / "merged.mid"))
    json.dump(by_stem, open(d / "merged_stems.json", "w"))
    for f in stems.glob("*.wav"):
        f.unlink()
    stems.rmdir()
    s = score_song(ref, d / "merged.mid", by_stem)
    s["seconds"] = {"separation": round(t_sep, 1), "transcription": round(t_tr, 1)}
    json.dump(s, open(d / "scores.json", "w"), indent=1)
    log(f"{song} {method}: multi F1 {s['multi']['f1']:.4f}, onset F1 {s['onset']['f1']:.4f} "
        f"(sep {t_sep:.0f}s, transcribe {t_tr:.0f}s)")


def summary(songs):
    rows = []
    for song in songs:
        ref = ROOT / "refs" / "RWC-P" / f"{song}.mid"
        base = ROOT / "base" / song / "muscriptor.mid"
        bdir = ROOT / "results" / "none" / song
        if base.exists() and not (bdir / "scores.json").exists():
            bdir.mkdir(parents=True, exist_ok=True)
            json.dump(score_song(ref, base), open(bdir / "scores.json", "w"), indent=1)
        for method in ("none",) + METHODS:
            p = ROOT / "results" / method / song / "scores.json"
            if not p.exists():
                continue
            s = json.load(open(p))
            row = {"song": song, "method": method}
            for k in ("onset", "offset", "frame", "drums", "multi"):
                row[k] = round(s[k]["f1"], 4)
            for f in FAMILIES:
                v = s["family_onset"][f]["f1"]
                row[f"{f}_onset"] = "" if v is None else round(v, 4)
            row.update(s.get("seconds", {}))
            rows.append(row)
    if rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(ROOT / "results" / "summary.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, keys)
            w.writeheader()
            w.writerows(rows)
    return rows


def main():
    songs = [s.strip() for s in open(sys.argv[1]) if s.strip()]
    methods = sys.argv[2].split(",") if len(sys.argv) > 2 else METHODS
    from muscriptor.transcription_model import TranscriptionModel
    log("loading MuScriptor large")
    model = TranscriptionModel.load_model(weights_path=MODEL, device="cuda", dtype=None)
    for method in methods:
        for song in songs:
            ref = ROOT / "refs" / "RWC-P" / f"{song}.mid"
            try:
                run_method(model, song, method, ref)
            except Exception as e:  # noqa: BLE001
                log(f"{song} {method}: FAILED {type(e).__name__}: {str(e)[:300]}")
            summary(songs)
    rows = summary(songs)
    log(f"ALL DONE: {len(rows)} rows in {ROOT / 'results' / 'summary.csv'}")


if __name__ == "__main__":
    main()
