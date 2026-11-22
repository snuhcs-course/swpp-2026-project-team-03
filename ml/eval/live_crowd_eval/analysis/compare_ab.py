#!/usr/bin/env python3
"""A(원본) vs B(crowd 제거본) 파이프라인 결과 비교. 정답이 없으므로 'B에서 무엇이 얼마나 바뀌었나'만 잰다.
출력: analysis/ab_inst.csv (곡×악기), analysis/ab_song.csv (곡)"""
import csv, json, sys
from pathlib import Path
import numpy as np, pretty_midi, mir_eval

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
INSTS = ["drums", "bass", "guitar", "piano"]
crowd = {r["id"]: r for r in csv.DictReader(open(ROOT / "crowd_metrics.csv"))}
man = {r["id"]: r for r in csv.DictReader(open(ROOT / "manifest.csv", encoding="utf-8"))}

def notes(p):
    if not p.exists(): return np.zeros((0, 2)), np.zeros(0)
    m = pretty_midi.PrettyMIDI(str(p))
    ns = [n for i in m.instruments for n in i.notes if n.end > n.start]
    if not ns: return np.zeros((0, 2)), np.zeros(0)
    iv = np.array([[n.start, max(n.end, n.start + 0.01)] for n in ns])
    pc = np.array([pretty_midi.note_number_to_hz(n.pitch) for n in ns])
    return iv, pc

def j(p, default=None):
    try: return json.load(open(p))
    except Exception: return default

# 사용법: python3 compare_ab.py            → A vs B (ab_*.csv)
#         python3 compare_ab.py A A2      → A vs A2, 같은 입력 반복 실행 (A_A2_*.csv)
X, Y = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("A", "B")
ins_rows, song_rows = [], []
for d in sorted((OUT / X).iterdir()):
    sid = d.name; a, b = OUT / X / sid, OUT / Y / sid
    if not b.exists(): continue
    ga, gb = j(a / "note_gate.json", {}).get("stems", {}), j(b / "note_gate.json", {}).get("stems", {})
    tot_a = tot_b = tot_m = 0
    for inst in INSTS:
        ia, pa = notes(a / "stem_midi_gated" / f"{inst}.mid")
        ib, pb = notes(b / "stem_midi_gated" / f"{inst}.mid")
        m = len(mir_eval.transcription.match_notes(ia, pa, ib, pb, onset_tolerance=0.05, offset_ratio=None)) if len(ia) and len(ib) else 0
        f1 = 2 * m / (len(ia) + len(ib)) if len(ia) + len(ib) else 1.0
        tot_a += len(ia); tot_b += len(ib); tot_m += m
        ins_rows.append(dict(id=sid, inst=inst, notes_A=len(ia), notes_B=len(ib),
                             change_pct=round(100 * (len(ib) - len(ia)) / len(ia), 1) if len(ia) else "",
                             onset_pitch_F1=round(f1, 3), only_A=len(ia) - m, only_B=len(ib) - m,
                             faint_A=ga.get(inst, {}).get("faint"), faint_B=gb.get(inst, {}).get("faint")))
    ba, bb = j(a / "beats.json", {}), j(b / "beats.json", {})
    A_b, B_b = np.array(ba.get("beats", [])), np.array(bb.get("beats", []))
    A_d, B_d = np.array(ba.get("downbeats", [])), np.array(bb.get("downbeats", []))
    bpm = lambda x: round(60 / np.median(np.diff(x)), 1) if len(x) > 2 else ""
    def meter(bt, db):
        if len(db) < 3: return ""
        c = [int(((bt >= s) & (bt < e)).sum()) for s, e in zip(db[:-1], db[1:])]
        return int(np.bincount(c).argmax())
    ica, icb = j(a / "input_check.json", {}), j(b / "input_check.json", {})
    sa, sb = ica.get("stem_share", {}), icb.get("stem_share", {})
    gena, genb = j(a / "generation.json", {}), j(b / "generation.json", {})
    sta, stb = j(a / "guitar_stereo.json", {}), j(b / "guitar_stereo.json", {})
    c = crowd.get(sid, {})
    song_rows.append(dict(
        id=sid, group=man.get(sid, {}).get("group"), song=f"{man.get(sid,{}).get('artist','')} - {man.get(sid,{}).get('song','')}",
        crowd_ratio_db=c.get("crowd_ratio_db"), crowd_sec_frac=c.get("crowd_sec_frac"),
        notes_A=tot_a, notes_B=tot_b, notes_change_pct=round(100 * (tot_b - tot_a) / tot_a, 1) if tot_a else "",
        all_onset_pitch_F1=round(2 * tot_m / (tot_a + tot_b), 3) if tot_a + tot_b else "",
        beat_F=round(mir_eval.beat.f_measure(A_b, B_b), 3) if len(A_b) and len(B_b) else "",
        downbeat_F=round(mir_eval.beat.f_measure(A_d, B_d), 3) if len(A_d) and len(B_d) else "",
        bpm_A=bpm(A_b), bpm_B=bpm(B_b), meter_A=meter(A_b, A_d), meter_B=meter(B_b, B_d),
        two_guitars_A=sta.get("two_guitars"), two_guitars_B=stb.get("two_guitars"),
        missing_A="|".join(gena.get("missing", [])), missing_B="|".join(genb.get("missing", [])),
        band_ratio_A=ica.get("band_ratio"), band_ratio_B=icb.get("band_ratio"),
        vocals_share_A=sa.get("vocals"), vocals_share_B=sb.get("vocals"),
        other_share_A=sa.get("other"), other_share_B=sb.get("other")))

pre = "ab" if (X, Y) == ("A", "B") else f"{X}_{Y}"
for name, rows in ((f"{pre}_inst.csv", ins_rows), (f"{pre}_song.csv", song_rows)):
    with open(ROOT / "analysis" / name, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(song_rows), "songs")
