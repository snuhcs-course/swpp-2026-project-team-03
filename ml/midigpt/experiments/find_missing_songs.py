"""
[P12] 실제로 4대 악기 중 일부가 '없는' 대중음악 MIDI 찾기 (Lakh MIDI clean_midi 사용)

하는 일
  1) clean_midi/<아티스트>/<곡>.mid 를 전부 훑어서 피아노·기타·베이스·드럼이 있는지 확인
  2) 4대 악기 중 정확히 1개만 없는 곡(나머지 3개는 충분히 있음)을 골라 목록 저장
     → missing_songs.csv
  3) 실제 편곡에서도 그 악기가 없기로 유명한 곡(아래 KNOWN)을 맨 위로 올리고,
     악기별로 몇 곡씩 missing_picks/<없는 악기>/ 로 복사

기준
  '있음' = 그 악기 음이 MIN_NOTES(기본 100)개 이상
  '없음' = 그 악기 음이 0개 (몇 개만 있는 애매한 곡은 제외)
  트랙이 너무 많으면 생성이 약해지므로 MAX_TRACKS(기본 12) 이하만

사용법 (Colab)
  python find_missing_songs.py clean_midi                # 악기별 5곡씩 복사
  ROCKY_PICK=10 python find_missing_songs.py clean_midi  # 악기별 10곡
"""
import csv
import os
import re
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

import mido

MIN_NOTES = int(os.environ.get("ROCKY_MIN_NOTES", "100"))
MAX_TRACKS = int(os.environ.get("ROCKY_MAX_TRACKS", "12"))
PICK = int(os.environ.get("ROCKY_PICK", "5"))
OUT_DIR = "missing_picks"
INSTS = ["piano", "guitar", "bass", "drums"]

# 원곡 편곡에서도 그 악기가 없는 것으로 알려진 곡 (MIDI 제작자가 넣었을 수도 있어 실제 확인은 스크립트가 함)
KNOWN = {
    "piano":  [("nirvana", "smells like teen spirit"), ("nirvana", "come as you are"),
               ("green day", "basket case"), ("foo fighters", "everlong"), ("weezer", "buddy holly"),
               ("ac/dc", "back in black"), ("ac dc", "back in black"), ("metallica", "enter sandman"),
               ("red hot chili peppers", "")],
    "guitar": [("keane", ""), ("ben folds five", ""), ("ben folds", "")],
    "bass":   [("white stripes", "seven nation army"), ("white stripes", ""),
               ("doors", "light my fire"), ("doors", "break on through"), ("doors", "")],
    "drums":  [("simon", "sound of silence"), ("simon", "scarborough fair"),
               ("beatles", "yesterday"), ("beatles", "blackbird"), ("beatles", "eleanor rigby"),
               ("kansas", "dust in the wind")],
}


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


def scan(path):
    """→ dict(악기별 음 수, 트랙 수, 길이) 또는 None(읽기 실패)"""
    try:
        mid = mido.MidiFile(path, clip=True)
        counts = {k: 0 for k in INSTS + ["other"]}
        parts = 0
        for track in mid.tracks:
            prog = {}
            notes = {}
            for msg in track:
                if msg.type == "program_change":
                    prog.setdefault(msg.channel, msg.program)
                elif msg.type == "note_on" and msg.velocity > 0:
                    notes[msg.channel] = notes.get(msg.channel, 0) + 1
            for ch, n in notes.items():
                counts[classify(prog.get(ch, 0), ch == 9)] += n
                parts += 1
        return dict(counts=counts, parts=parts, seconds=round(mid.length))
    except Exception:
        return None


def known_rank(inst, artist, title):
    a, t = artist.lower(), title.lower()
    for i, (ka, kt) in enumerate(KNOWN[inst]):
        if ka in a and kt in t:
            return i if kt else 100 + i        # 곡명까지 맞으면 더 위로
    return 9999


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    root = sys.argv[1]
    files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if f.lower().endswith((".mid", ".midi"))]
    print(f"MIDI {len(files)}개 검사 중... (몇 분 걸려요)")
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(scan, files, chunksize=64))

    rows, seen = [], set()
    for path, r in zip(files, results):
        if not r or r["parts"] > MAX_TRACKS or not (90 <= r["seconds"] <= 480):
            continue
        c = r["counts"]
        missing = [k for k in INSTS if c[k] == 0]
        present = [k for k in INSTS if c[k] >= MIN_NOTES]
        if len(missing) != 1 or len(present) != 3:
            continue
        artist = os.path.basename(os.path.dirname(path))
        title = re.sub(r"\.\d+$", "", os.path.splitext(os.path.basename(path))[0])   # 'Song.1' 같은 중복본 정리
        key = (artist.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(missing=missing[0], artist=artist, title=title, tracks=r["parts"], seconds=r["seconds"],
                         piano=c["piano"], guitar=c["guitar"], bass=c["bass"], drums=c["drums"], other=c["other"],
                         known=known_rank(missing[0], artist, title) < 9999, path=path,
                         _rank=known_rank(missing[0], artist, title)))

    rows.sort(key=lambda x: (x["missing"], x["_rank"], x["tracks"], x["artist"].lower()))
    fields = [k for k in rows[0] if not k.startswith("_")] if rows else []
    with open("missing_songs.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    kor = {"piano": "피아노", "guitar": "기타", "bass": "베이스", "drums": "드럼"}
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    print(f"\n조건에 맞는 곡 {len(rows)}개 → missing_songs.csv\n")
    for inst in INSTS:
        group = [r for r in rows if r["missing"] == inst]
        os.makedirs(os.path.join(OUT_DIR, inst), exist_ok=True)
        print(f"■ {kor[inst]} 없는 곡: {len(group)}개 (★ = 원곡 편곡에서도 없는 것으로 알려진 곡)")
        for r in group[:PICK]:
            name = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", f"{r['artist']}-{r['title']}")[:80] + ".mid"
            shutil.copy2(r["path"], os.path.join(OUT_DIR, inst, name))
            print(f"   {'★' if r['known'] else ' '} {r['artist']} - {r['title']}  "
                  f"(트랙 {r['tracks']}, {r['seconds'] // 60}분 {r['seconds'] % 60}초)")
        print()
    print(f"복사 위치 → {OUT_DIR}/<없는 악기>/  (다른 곡을 쓰려면 missing_songs.csv 에서 골라 path 의 파일을 쓰면 돼요)")


if __name__ == "__main__":
    main()
