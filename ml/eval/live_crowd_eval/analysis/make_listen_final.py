#!/usr/bin/env python3
"""청취 판정 v2: 기준 = 해당 악기의 분리된 stem(원본에서 BS-RoFormer로 분리), X/Y = 채보한 음만 그 악기 음색으로 연주.
구간은 v1과 같음(answer_key_A_B.csv의 start_sec). X/Y 배정은 새로 섞고 정답은 answer_key_v2_<X>_<Y>.csv에 둠.
사용: python3 analysis/make_listen_v2.py [A] [B]   (stem: listen_stems/<id>_<악기>.flac 필요)"""
import csv, random, shutil, sys
from pathlib import Path
import numpy as np, soundfile as sf, pretty_midi, tinysoundfont

ROOT = Path(__file__).resolve().parents[1]; AN = ROOT / "analysis"
X, Y = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("A", "B")
SR, WIN = 44100, 30.0
PROGRAM = {"bass": 33, "guitar": 27, "piano": 0}   # GM: Finger Bass, Clean Guitar, Grand Piano
out = AN / f"listen_{X}_{Y}"; out.mkdir(exist_ok=True)
CASES = [("L01", "bass"), ("L12", "bass"), ("L04", "guitar"), ("L04", "bass"), ("P04", "bass"),
         ("P05", "piano"), ("P08", "guitar"), ("L16", "guitar"), ("P06", "bass")]
import mir_eval
def onsets(arm, sid, inst):
    m = pretty_midi.PrettyMIDI(str(ROOT / "out" / arm / sid / "stem_midi_gated" / f"{inst}.mid"))
    ns = [n for i in m.instruments for n in i.notes]
    if not ns: return np.zeros((0, 2)), np.zeros(0)
    return (np.array([[n.start, max(n.end, n.start + .01)] for n in ns]), np.array([pretty_midi.note_number_to_hz(n.pitch) for n in ns]))
starts = {}
for k, (sid, inst) in enumerate(CASES, 1):   # X/Y 채보 차이가 가장 큰 30초 구간
    ia, pa = onsets(X, sid, inst); ib, pb = onsets(Y, sid, inst)
    mt = mir_eval.transcription.match_notes(ia, pa, ib, pb, onset_tolerance=0.05, offset_ratio=None) if len(ia) and len(ib) else []
    ma, mb = {i for i, _ in mt}, {j for _, j in mt}
    dt = [ia[i, 0] for i in range(len(ia)) if i not in ma] + [ib[j, 0] for j in range(len(ib)) if j not in mb]
    dur = sf.info(str(ROOT / "wav" / f"{sid}.wav")).duration
    cand = np.arange(0, max(dur - WIN, 0) + 1e-9, 5.0)
    cnt = [sum(c <= t < c + WIN for t in dt) for c in cand]
    starts[f"{k:02d}_{sid}_{inst}"] = float(cand[int(np.argmax(cnt))])
rnd = random.Random(11)

def render(notes, t0, program):
    s = tinysoundfont.Synth(samplerate=SR); sfid = s.sfload(str(AN / "sf" / "GeneralUser-GS.sf2"))
    s.program_select(0, sfid, 0, program)
    ev = []
    for n in notes:
        a, b = n.start - t0, n.end - t0
        if b <= 0 or a >= WIN: continue
        ev += [(max(a, 0), 1, n.pitch, n.velocity), (min(b, WIN), 0, n.pitch, 0)]
    ev.sort(key=lambda e: (e[0], e[1]))
    buf, pos = [], 0
    for t, on, p, v in ev:
        k = int(t * SR)
        if k > pos: buf.append(np.frombuffer(s.generate(k - pos), np.float32).reshape(-1, 2)); pos = k
        (s.noteon(0, p, max(v, 60)) if on else s.noteoff(0, p))
    n = int(WIN * SR)
    if n > pos: buf.append(np.frombuffer(s.generate(n - pos), np.float32).reshape(-1, 2))
    return np.concatenate(buf)[:n] if buf else np.zeros((n, 2), np.float32)

def norm(x, peak=0.7):
    m = np.abs(x).max(); return x / m * peak if m > 0 else x

key = []
for case, t0 in starts.items():
    _, sid, inst = case.split("_")
    stem, sr = sf.read(ROOT / "listen_stems" / f"{sid}_{inst}.flac", always_2d=True)
    seg = stem[int(t0 * sr): int(t0 * sr) + int(WIN * sr)]
    sf.write(out / f"{case}_0_stem.wav", norm(seg), SR)
    arms = [X, Y]; rnd.shuffle(arms)
    for lab, arm in zip("XY", arms):
        m = pretty_midi.PrettyMIDI(str(ROOT / "out" / arm / sid / "stem_midi_gated" / f"{inst}.mid"))
        ns = [n for i in m.instruments for n in i.notes]
        sf.write(out / f"{case}_{lab}.wav", norm(render(ns, t0, PROGRAM[inst])), SR)
    key.append(dict(case=case, start_sec=t0, X=arms[0], Y=arms[1])); print(case, arms)
with open(AN / f"answer_key_v2_{X}_{Y}.csv", "w", newline="") as fp:
    w = csv.DictWriter(fp, fieldnames=list(key[0])); w.writeheader(); w.writerows(key)
NAMES = {"L01": "Red Hot Chili Peppers - Can't Stop (라이브)", "L12": "Journey - Don't Stop Believin' (라이브)",
         "L04": "The White Stripes - Seven Nation Army (라이브)", "P04": "버스커버스커 - 여수 밤바다 (버스킹 직캠)",
         "P05": "실리카겔 - Desert Eagle (페스티벌 라이브)", "P08": "무한궤도 - 그대에게 (1988 방송)",
         "L16": "The Killers - Mr. Brightside (라이브)", "P06": "Green Day - 21 Guns (라이브)"}
KO = {"bass": "베이스", "guitar": "기타", "piano": "피아노"}
with open(out / "judge_sheet.csv", "w", newline="", encoding="utf-8-sig") as fp:
    w = csv.writer(fp); w.writerow(["번호", "파일 이름 앞부분", "곡", "악기", "원본 구간(초)", "더 가까운 쪽 (X / Y / 비슷)", "이유·메모"])
    for case, t0 in starts.items():
        n, sid, inst = case.split("_"); w.writerow([n, case, NAMES[sid], KO[inst], f"{t0:.0f}~{t0 + WIN:.0f}", "", ""])
shutil.copy(AN / "판정_안내_v2.txt", out / "00_판정_안내.txt")
print("만든 폴더:", out)
