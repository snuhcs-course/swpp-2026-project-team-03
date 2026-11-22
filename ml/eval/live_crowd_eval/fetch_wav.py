#!/usr/bin/env python3
"""manifest.csv의 30곡을 유튜브에서 받아 44.1 kHz 스테레오 16-bit wav로 변환한다.

- url 칸이 비어 있으면 query로 유튜브 검색 1순위 영상을 받는다(ytsearch1).
- 원본 오디오 스트림(webm/m4a)은 raw/에 재인코딩 없이 보관하고, wav는 wav/에 만든다.
- 실제로 받은 영상의 URL·제목·채널·길이는 resolved.csv에 기록한다.
  → 제목을 확인하고, 원하는 영상이 아니면 manifest.csv의 url 칸에 직접 URL을 넣고 해당 wav를 지운 뒤 다시 실행.
- 이미 wav가 있는 곡은 건너뛰므로 중간에 끊겨도 다시 실행하면 이어서 받는다.
"""
import csv, shutil, subprocess, sys
from urllib.parse import quote_plus
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW, WAV = HERE / "raw", HERE / "wav"
MAX_SEC = 360  # 6분 넘는 영상(풀 콘서트·긴 인트로 등)은 거른다

def need(tool):
    if not shutil.which(tool):
        sys.exit(f"{tool}이 없어. 먼저 설치해: brew install {tool}")

def main():
    need("yt-dlp"); need("ffmpeg")
    RAW.mkdir(exist_ok=True); WAV.mkdir(exist_ok=True)
    rows = list(csv.DictReader(open(HERE / "manifest.csv", encoding="utf-8")))
    only = set(sys.argv[1:])  # 예: python3 fetch_wav.py L03 S05
    log_path = HERE / "resolved.csv"
    old = {}
    if log_path.exists():
        old = {r["id"]: r for r in csv.DictReader(open(log_path, encoding="utf-8"))}

    for r in rows:
        rid = r["id"]
        if only and rid not in only:
            continue
        wav = WAV / f"{rid}.wav"
        if wav.exists():
            print(f"[skip] {rid} 이미 있음"); continue
        if (r.get("local") or "").strip():  # 로컬 파일 행: 다운로드 없이 변환만
            lp = Path(r["local"]).expanduser()
            f = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(lp),
                                "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
            print(f"[{'ok' if f.returncode == 0 else 'fail':4}] {rid}: 로컬 변환 {lp.name}")
            continue
        extra = (r.get("filter") or "").strip()
        max_sec = int(r.get("max_sec") or MAX_SEC)  # 곡별 예외가 있으면 그 값
        n = 10 if extra else 5  # 상위 n개 중 조건을 모두 통과한 첫 영상
        if r["url"].strip():
            src = r["url"].strip()
        elif (r.get("search") or "") == "ytmusic":  # 유튜브 뮤직 '노래' 탭 = 음반 원곡(Topic) 트랙
            src = f"https://music.youtube.com/search?q={quote_plus(r['query'])}#songs"
        else:
            src = f"ytsearch{n}:{r['query']}"
        # filter 칸의 " || "는 OR: 조건 묶음 중 하나라도 통과하면 받는다
        mfs = [f"duration < {max_sec}" + (f" & {e.strip()}" if e.strip() else "") for e in (extra.split(" || ") if extra else [""])]
        mf = " || ".join(mfs)
        print(f"[get ] {rid} ← {src}")
        cmd = ["yt-dlp", "--no-playlist", "-f", "bestaudio", "--max-downloads", "1", "--playlist-end", str(n),
               "--retries", "5", "--fragment-retries", "5",
               *[a for m in mfs for a in ("--match-filter", m)],
               "-o", str(RAW / f"{rid}.%(ext)s"), "--no-simulate",
               "--print", "after_move:%(filepath)s\t%(webpage_url)s\t%(title)s\t%(channel)s\t%(duration)s",
               src]
        p = subprocess.run(cmd, capture_output=True, text=True)
        lines = [l for l in p.stdout.splitlines() if l.count("\t") == 4]
        if p.returncode not in (0, 101) or not lines:  # 101 = --max-downloads 도달(정상)
            print(f"[fail] {rid}: {p.stderr.strip()[-300:] or f'상위 {n}개 검색 결과 중 조건({mf})을 통과한 영상 없음'}")
            old[rid] = {"id": rid, "status": "download_fail", "url": "", "title": "", "channel": "", "duration_s": "",
                        "error": " ".join(p.stderr.strip().splitlines()[-3:])[-400:] or f"상위 {n}개 중 조건({mf}) 통과 영상 없음"}
            continue
        fpath, url, title, channel, dur = lines[-1].split("\t")
        f = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", fpath,
                            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
        status = "ok" if f.returncode == 0 else "convert_fail"
        old[rid] = {"id": rid, "status": status, "url": url, "title": title,
                    "channel": channel, "duration_s": dur, "error": ""}
        print(f"[{status:4}] {rid}: {title} ({channel}, {dur}s)")

    with open(log_path, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=["id", "status", "url", "title", "channel", "duration_s", "error"], extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            if r["id"] in old:
                w.writerow(old[r["id"]])
    print(f"\n기록: {log_path}")

if __name__ == "__main__":
    main()
