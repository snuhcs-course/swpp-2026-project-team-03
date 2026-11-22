#!/usr/bin/env python3
"""C 채보에서 관중 구간(crowd가 음악보다 6 dB 이상 큰 1초 구간)에 시작하는 음을 지워 out/Cm을 만든다.
박·기타 판정 등 나머지 파일은 C를 그대로 복사. 사용: python3 analysis/mask_c.py  (crowd_secs.json 필요)"""
import json, shutil
from pathlib import Path
import pretty_midi
ROOT = Path(__file__).resolve().parents[1]
secs = json.load(open(ROOT / "crowd_secs.json"))
src, dst = ROOT / "out" / "C", ROOT / "out" / "Cm"
removed = {}
for sid, d in secs.items():
    if not (src / sid).exists(): continue
    if (dst / sid).exists(): shutil.rmtree(dst / sid)
    shutil.copytree(src / sid, dst / sid)
    mask = set(d["crowd"])
    for p in (dst / sid / "stem_midi_gated").glob("*.mid"):
        m = pretty_midi.PrettyMIDI(str(p)); k = 0
        for inst in m.instruments:
            keep = [n for n in inst.notes if int(n.start) not in mask]; k += len(inst.notes) - len(keep); inst.notes = keep
        m.write(str(p)); removed[f"{sid}/{p.stem}"] = k
print("지운 음 합계:", sum(removed.values()), {k: v for k, v in removed.items() if v})
