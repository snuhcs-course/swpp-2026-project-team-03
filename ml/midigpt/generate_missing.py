"""
ROCKY 파이프라인 — 원곡에 없는 악기 파트를 MIDI-GPT로 생성

입력  : 채보·박자 정렬이 끝난 MIDI 한 곡 (Demucs → MuScriptor → Beat This! 결과)
        + 새로 만들 악기 (piano / guitar / bass / drums 중 하나 이상)
출력  : <출력폴더>/<곡이름>__+<악기>_band.mid   원곡 트랙 전부 + 생성한 악기
        <출력폴더>/<곡이름>__+<악기>_only.mid   생성한 악기 파트만

규칙
  - 원곡에 있던 트랙은 하나도 지우지 않아요. 같은 악기로 분류된 트랙이 이미 있어도
    (예: 신스가 기타 번호로 저장된 경우) 그대로 두고 새 파트를 '추가'해요.
  - 악기를 여러 개 고르면 악기마다 따로 생성해요 (결과 파일도 악기마다 따로).
  - 같은 입력·같은 seed(ROCKY_SEED)면 같은 결과가 나와요.

사용법 (ml/midigpt 폴더에서)
  python generate_missing.py 곡.mid piano
  python generate_missing.py 곡.mid piano guitar --out results_dir
  python generate_missing.py --jobs jobs.csv --out results_dir
      jobs.csv 형식 (첫 줄은 제목):  file,instruments
                                      songs/time-bomb.mid,piano
                                      songs/yoru.mid,guitar;bass

환경 변수: ROCKY_SEED(기본 0), ROCKY_MODEL(기본 yellow_medium), ROCKY_DEVICE(cuda/cpu), ROCKY_BARS(0=곡 전체)
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INSTRUMENTS = ("piano", "guitar", "bass", "drums")


def run(cmd, env):
    """하위 스크립트 실행. 출력은 그대로 보여주고 실패하면 멈춰요."""
    r = subprocess.run(cmd, env=dict(os.environ, **env), text=True)
    if r.returncode != 0:
        raise RuntimeError(f"실패: {' '.join(cmd)}")


def generate(midi_path, insts, out_dir, work_dir):
    base = os.path.splitext(os.path.basename(midi_path))[0]
    prep_dir = os.path.join(work_dir, "prep")
    shutil.rmtree(work_dir, ignore_errors=True)

    # 1) 악기별 파일로 나누기 (piano.mid, guitar.mid, bass.mid, drums.mid, other_XX.mid)
    run([sys.executable, os.path.join(HERE, "prep_song.py"), midi_path], {"ROCKY_PREP_OUT": prep_dir})
    song = os.listdir(prep_dir)[0]

    results = []
    for inst in insts:
        in_dir = os.path.join(work_dir, f"in_{inst}")
        gen_dir = os.path.join(work_dir, f"out_{inst}")
        song_in = os.path.join(in_dir, song)
        shutil.copytree(os.path.join(prep_dir, song), song_in)

        # 2) 이미 같은 악기로 분류된 트랙은 지우지 않고 'other'로 남김
        existing = os.path.join(song_in, "MIDI", f"{inst}.mid")
        if os.path.exists(existing):
            os.rename(existing, os.path.join(song_in, "MIDI", f"other_existing_{inst}.mid"))
            print(f"  기존 '{inst}' 트랙은 그대로 두고 새 파트를 추가해요")

        # 3) MIDI-GPT 생성
        run([sys.executable, os.path.join(HERE, "generate_part.py"), in_dir],
            {"ROCKY_INST": inst, "ROCKY_OUT": gen_dir, "ROCKY_LOG": os.path.join(work_dir, "log.csv")})

        # 4) 결과 모으기
        src = os.path.join(gen_dir, song, inst)
        band = os.path.join(src, "generated.mid")
        only = os.path.join(src, "generated_only.mid")
        if not os.path.exists(band):
            print(f"  ⚠ {base} + {inst}: 생성 실패 (log.csv 확인)")
            results.append((base, inst, "fail", ""))
            continue
        os.makedirs(out_dir, exist_ok=True)
        dst_band = os.path.join(out_dir, f"{base}__+{inst}_band.mid")
        shutil.copy(band, dst_band)
        shutil.copy(only, os.path.join(out_dir, f"{base}__+{inst}_only.mid"))
        results.append((base, inst, "ok", dst_band))
    return results


def read_jobs(path):
    jobs = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            insts = [i.strip() for i in row["instruments"].replace(",", ";").split(";") if i.strip()]
            jobs.append((row["file"].strip(), insts))
    return jobs


def main():
    ap = argparse.ArgumentParser(description="원곡에 없는 악기 파트를 MIDI-GPT로 생성")
    ap.add_argument("midi", nargs="?", help="입력 MIDI 파일")
    ap.add_argument("instruments", nargs="*", help="새로 만들 악기: piano guitar bass drums")
    ap.add_argument("--jobs", help="여러 곡을 한 번에: file,instruments 열이 있는 CSV")
    ap.add_argument("--out", default="gen_results", help="결과 폴더 (기본 gen_results)")
    ap.add_argument("--work", default="gen_work", help="중간 파일 폴더 (기본 gen_work)")
    a = ap.parse_args()

    jobs = read_jobs(a.jobs) if a.jobs else [(a.midi, a.instruments)]
    if not jobs or not jobs[0][0]:
        ap.error("MIDI 파일과 악기를 주거나 --jobs 를 주세요")

    summary = []
    for i, (path, insts) in enumerate(jobs):
        bad = [x for x in insts if x not in INSTRUMENTS]
        if not os.path.exists(path) or not insts or bad:
            print(f"⚠ 건너뜀: {path} (파일 없음 또는 악기 이름 확인: {insts})")
            summary.append((os.path.basename(path), ",".join(insts), "skip", ""))
            continue
        print(f"\n===== [{i + 1}/{len(jobs)}] {os.path.basename(path)} → {', '.join(insts)}")
        summary += generate(path, insts, a.out, os.path.join(a.work, str(i)))

    print("\n===== 요약")
    for base, inst, status, out in summary:
        print(f"  {status:<4} {base} + {inst}  {out}")


if __name__ == "__main__":
    main()
