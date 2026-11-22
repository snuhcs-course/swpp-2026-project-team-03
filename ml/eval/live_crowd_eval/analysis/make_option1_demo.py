#!/usr/bin/env python3
"""옵션 1 데모: A(원본 채보)와 옵션 1(A + 관중 구간 마스킹)을 곡 전체 MIDI·MP3로 만든다.
MIDI는 악기별 채보(stem_midi_gated)를 합친 것 = 박 정렬·악보 생성 전 단계.
사용: python3 analysis/make_option1_demo.py L01 L16 ...   → analysis/demo_option1/<id>/"""
import csv, json, subprocess, sys, tempfile, os
from pathlib import Path
import numpy as np, soundfile as sf, pretty_midi, tinysoundfont

ROOT = Path(__file__).resolve().parents[1]; AN = ROOT / "analysis"; SR = 44100
SF2 = AN / "sf" / "GeneralUser-GS.sf2"
INSTS = {"drums": (0, True), "bass": (33, False), "guitar": (27, False), "piano": (0, False)}
CH = {"drums": 9, "bass": 0, "guitar": 1, "piano": 2}
secs = json.load(open(ROOT / "crowd_secs.json"))
man = {r["id"]: r for r in csv.DictReader(open(ROOT / "manifest.csv", encoding="utf-8"))}

def build(sid, mask):
    pm, removed = pretty_midi.PrettyMIDI(), []
    for inst, (prog, drum) in INSTS.items():
        m = pretty_midi.PrettyMIDI(str(ROOT / "out" / "A" / sid / "stem_midi_gated" / f"{inst}.mid"))
        track = pretty_midi.Instrument(program=prog, is_drum=drum, name=inst)
        for i in m.instruments:
            for n in i.notes:
                if int(n.start) in mask: removed.append((round(n.start, 2), inst, pretty_midi.note_number_to_name(n.pitch) if not drum else f"drum {n.pitch}"))
                else: track.notes.append(n)
        pm.instruments.append(track)
    return pm, removed

def render(pm, dur):
    s = tinysoundfont.Synth(samplerate=SR); sfid = s.sfload(str(SF2))
    for inst, (prog, drum) in INSTS.items(): s.program_select(CH[inst], sfid, 128 if drum else 0, prog, is_drums=drum)
    ev = []
    for tr in pm.instruments:
        c = CH[tr.name]
        for n in tr.notes: ev += [(n.start, 1, c, n.pitch, n.velocity), (n.end, 0, c, n.pitch, 0)]
    ev.sort(key=lambda e: (e[0], e[1])); out, pos = [], 0
    for t, on, c, p, v in ev:
        k = int(t * SR)
        if k > pos: out.append(np.frombuffer(s.generate(k - pos), np.float32).reshape(-1, 2)); pos = k
        s.noteon(c, p, max(v, 50)) if on else s.noteoff(c, p)
    n = int(dur * SR)
    if n > pos: out.append(np.frombuffer(s.generate(n - pos), np.float32).reshape(-1, 2))
    y = np.concatenate(out)[:n]; return y / (np.abs(y).max() + 1e-9) * 0.8

def mp3(wav_arr, path):
    fd, tmp = tempfile.mkstemp(suffix=".wav"); os.close(fd); sf.write(tmp, wav_arr, SR)   # 임시 파일은 폴더 밖에
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-b:a", "192k", str(path)], check=True); os.remove(tmp)

for sid in sys.argv[1:]:
    r = man[sid]; name = f"{sid}_{r['artist']} - {r['song']}".replace("/", "_")
    out = AN / "demo_option1" / name; out.mkdir(parents=True, exist_ok=True)
    mask = set(secs[sid]["crowd"]); dur = sf.info(str(ROOT / "wav" / f"{sid}.wav")).duration
    full, _ = build(sid, set()); opt1, removed = build(sid, mask)
    full.write(str(out / "1_현재앱_원본채보.mid")); opt1.write(str(out / "2_옵션1_관중구간마스킹.mid"))
    x, _ = sf.read(ROOT / "wav" / f"{sid}.wav"); mp3(x, out / "0_라이브원본.mp3")
    mp3(render(full, dur), out / "1_현재앱_원본채보.mp3"); mp3(render(opt1, dur), out / "2_옵션1_관중구간마스킹.mp3")
    with open(out / "지워진_음.csv", "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp); w.writerow(["시각(초)", "분:초", "악기", "음"])
        for t, inst, p in sorted(removed): w.writerow([t, f"{int(t//60)}:{t%60:05.2f}", inst, p])
    ranges = sorted(mask); print(name, "| 관중 구간(초):", ranges, "| 지운 음:", len(removed))
