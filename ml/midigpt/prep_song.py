"""
[P12] 아무 MIDI 곡(대중음악 등)을 5단계 입력 형식으로 바꾸는 준비 스크립트

하는 일
  곡.mid 하나 → my_songs/Track<이름>/MIDI/piano.mid, guitar.mid, bass.mid, drums.mid, other_XX.mid
  (5단계 generate_part.py 가 읽는 '형식 A' 폴더)

악기 분류 기준 (General MIDI 악기 번호)
  드럼   : 10번 채널(채널 9)       피아노 : 0~7 (어쿠스틱·일렉 피아노 등)
  기타   : 24~31                   베이스 : 32~39
  그 외  : other (보컬 멜로디·스트링·오르간·신스 등) → 실험할 때 항상 입력으로 남음

템포
  midigpt 는 곡 전체에 템포 1개만 써요. 원곡에 템포 변화가 있으면
  '가장 오래 유지되는 템포' 하나로 맞춰요 (음의 박자 위치는 그대로, 재생 속도만 통일).

사용법
  python prep_song.py 곡.mid                    # → my_songs/Track<파일이름>/
  python prep_song.py 곡1.mid 곡2.mid ...        # 여러 곡 한 번에
  ROCKY_PREP_OUT=폴더 python prep_song.py 곡.mid  # 저장 위치 변경
"""
import os
import re
import sys
import unicodedata
from collections import defaultdict

import mido

OUT = os.environ.get("ROCKY_PREP_OUT", "my_songs")
KOR = {"piano": "피아노", "guitar": "기타", "bass": "베이스", "drums": "드럼", "other": "기타 악기(other)"}


def classify(program, is_drum):
    if is_drum:
        return "drums"
    if 0 <= program <= 7:
        return "piano"
    if 24 <= program <= 31:
        return "guitar"
    if 32 <= program <= 39:
        return "bass"
    return "other"


def to_abs(track):
    t, out = 0, []
    for msg in track:
        t += msg.time
        out.append((t, msg))
    return out


def from_abs(events, name=None):
    tr = mido.MidiTrack()
    if name:
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
    last = 0
    for t, msg in sorted(events, key=lambda x: x[0]):
        tr.append(msg.copy(time=t - last))
        last = t
    tr.append(mido.MetaMessage("end_of_track", time=0))
    return tr


def split_parts(mid):
    """[(이름, 악기번호, 드럼여부, [(절대tick, 메시지)])] — 트랙 × 채널 단위로 나눔 (형식 0 파일도 처리)"""
    parts, meta = [], []
    for ti, track in enumerate(mid.tracks):
        name = next((m.name for m in track if m.type == "track_name"), f"track{ti}")
        by_ch = defaultdict(list)
        for t, msg in to_abs(track):
            if msg.is_meta:
                if msg.type in ("set_tempo", "time_signature", "key_signature"):
                    meta.append((t, msg))
            elif hasattr(msg, "channel"):
                by_ch[msg.channel].append((t, msg))
        for ch, ev in by_ch.items():
            if not any(m.type == "note_on" and m.velocity > 0 for _, m in ev):
                continue
            prog = next((m.program for _, m in ev if m.type == "program_change"), 0)
            parts.append((name, prog, ch == 9, ev))
    return parts, meta


def main_tempo(meta, end_tick, tpq):
    tempos = sorted((t, m.tempo) for t, m in meta if m.type == "set_tempo") or [(0, 500000)]
    dur = defaultdict(float)
    for i, (t, tempo) in enumerate(tempos):
        nxt = tempos[i + 1][0] if i + 1 < len(tempos) else end_tick
        dur[tempo] += max(nxt - t, 0) / tpq * tempo        # 실제 재생 시간 기준
    return max(dur, key=dur.get), len(tempos)


def prep(path):
    mid = mido.MidiFile(path)
    parts, meta = split_parts(mid)
    end_tick = max((t for *_, ev in parts for t, _ in ev), default=0)
    tempo, n_tempo = main_tempo(meta, end_tick, mid.ticks_per_beat)

    song = "Track" + re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", unicodedata.normalize("NFC", os.path.splitext(os.path.basename(path))[0]))
    mdir = os.path.join(OUT, song, "MIDI")
    os.makedirs(mdir, exist_ok=True)
    for f in os.listdir(mdir):
        os.remove(os.path.join(mdir, f))

    header = [(0, mido.MetaMessage("set_tempo", tempo=tempo, time=0))]
    header += [(t, m) for t, m in meta if m.type == "time_signature"]
    groups = defaultdict(list)
    for name, prog, drum, ev in parts:
        groups[classify(prog, drum)].append((name, prog, drum, ev))

    print(f"\n[{os.path.basename(path)}] → {os.path.join(OUT, song)}")
    print(f"  템포 {n_tempo}개 → {round(60e6 / tempo)} BPM 하나로 통일 | 해상도 {mid.ticks_per_beat}")
    other_i = 0
    for label in ("piano", "guitar", "bass", "drums", "other"):
        for name, prog, drum, ev in groups.get(label, []):
            n = sum(1 for _, m in ev if m.type == "note_on" and m.velocity > 0)
            print(f"  {KOR[label]:<14} ← {name} (악기 {prog}{', 드럼' if drum else ''}, 음 {n}개)")
        if not groups.get(label):
            continue
        if label == "other":                                    # other 는 트랙마다 파일 하나
            for name, prog, drum, ev in groups[label]:
                out = mido.MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)
                out.tracks += [from_abs(header), from_abs(ev, name)]
                out.save(os.path.join(mdir, f"other_{other_i:02d}.mid"))
                other_i += 1
        else:                                                   # 같은 악기 여러 개 → 한 파일에 여러 트랙
            out = mido.MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)
            out.tracks.append(from_abs(header))
            out.tracks += [from_abs(ev, name) for name, prog, drum, ev in groups[label]]
            out.save(os.path.join(mdir, f"{label}.mid"))
    missing = [KOR[k] for k in ("piano", "guitar", "bass", "drums") if not groups.get(k)]
    if missing:
        print(f"  ※ 원곡에 없는 악기: {', '.join(missing)} → 그 악기는 '정답 없이' 새로 생성돼요")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit()
    for p in sys.argv[1:]:
        prep(p)
    print(f"\n다음: python generate_part.py {OUT}")
