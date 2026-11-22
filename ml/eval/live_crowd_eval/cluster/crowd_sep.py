#!/usr/bin/env python3
"""Mel-Band RoFormer Crowd(aufr33·viperx)로 각 wav를 crowd / 나머지(음악)로 나눈다.

입력: WAV_DIR/*.wav (44.1 kHz 스테레오)
출력: OUT/cleaned/<id>.wav  관중 소리를 뺀 음악 = '나머지' stem, 입력과 같은 길이·44.1 kHz·스테레오·16-bit
      OUT/crowd/<id>.flac   관중 stem (청취 확인용)
      OUT/crowd_metrics.csv 곡별 판정 점수
        crowd_ratio_db : 곡 전체에서 crowd 에너지 / 원본 에너지 (dB)
        crowd_sec_frac : 1초 구간 중 crowd 에너지가 원본의 10%(-10 dB) 이상인 구간 비율
        crowd_peak_db  : 1초 구간별 crowd/원본 비율의 최댓값 (dB)
이미 cleaned가 있는 곡은 건너뛴다.
"""
import csv, os, sys, time, shutil, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf

MODEL = "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt"
EPS = 1e-12

def db(x):
    return 10 * np.log10(max(x, EPS))

def fit(x, n):
    """(n, 2)로 길이·채널 맞추기"""
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    x = x[:, :2] if x.shape[1] >= 2 else np.repeat(x, 2, 1)
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros((n - len(x), 2), x.dtype)])

def metrics(mix, crowd, sr):
    e = lambda a: float(np.mean(a.astype(np.float64) ** 2))
    ratio = db(e(crowd)) - db(e(mix))
    hop = sr
    fr = []
    for i in range(0, len(mix) - hop + 1, hop):
        em = e(mix[i:i + hop])
        if em < 1e-8:          # 무음 구간은 제외
            continue
        fr.append(db(e(crowd[i:i + hop])) - db(em))
    fr = np.array(fr) if fr else np.array([-120.0])
    return round(ratio, 2), round(float(np.mean(fr >= -10)), 3), round(float(fr.max()), 2)

def main(wav_dir, out_dir, model_dir):
    from audio_separator.separator import Separator
    wav_dir, out = Path(wav_dir), Path(out_dir)
    (out / "cleaned").mkdir(parents=True, exist_ok=True)
    (out / "crowd").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=out))
    sep = Separator(model_file_dir=model_dir, output_dir=str(tmp), output_format="WAV",
                    sample_rate=44100, use_soundfile=True,
                    normalization_threshold=1.0, amplification_threshold=0.0)  # 레벨을 바꾸지 않음
    sep.load_model(model_filename=MODEL)
    mpath = out / "crowd_metrics.csv"
    done = {}
    if mpath.exists():
        done = {r["id"]: r for r in csv.DictReader(open(mpath))}
    fields = ["id", "seconds_audio", "seconds_proc", "crowd_ratio_db", "crowd_sec_frac", "crowd_peak_db",
              "len_match", "status"]
    # 파이프라인을 돌릴 곡(pipeline_ids.txt)을 먼저 처리해서 B 실행이 빨리 시작되게 함
    pri = Path(wav_dir).parent / "pipeline_ids.txt"
    order = [l.strip() for l in open(pri)] if pri.exists() else []
    rank = {k: i for i, k in enumerate(order)}
    for wav in sorted(wav_dir.glob("*.wav"), key=lambda w: (rank.get(w.stem, 999), w.stem)):
        rid = wav.stem
        if (out / "cleaned" / f"{rid}.wav").exists() and rid in done:
            print(f"[skip] {rid}", flush=True); continue
        t0 = time.time()
        row = {"id": rid, "status": "ok"}
        try:
            mix, sr = sf.read(wav, always_2d=True)
            n = len(mix)
            files = [Path(f) if os.path.isabs(f) else tmp / f for f in sep.separate(str(wav))]
            crowd_f = [f for f in files if "(crowd)" in f.name.lower()]
            other_f = [f for f in files if f not in crowd_f]
            if len(crowd_f) != 1 or len(other_f) != 1:
                raise RuntimeError(f"unexpected outputs: {[f.name for f in files]}")
            crowd, sr_c = sf.read(crowd_f[0], always_2d=True)
            other, sr_o = sf.read(other_f[0], always_2d=True)
            if not (sr == sr_c == sr_o == 44100):
                raise RuntimeError(f"sample rate mismatch {sr} {sr_c} {sr_o}")
            row["len_match"] = int(len(crowd) == n and len(other) == n)
            crowd, other, mix = fit(crowd, n), fit(other, n), fit(mix, n)
            # 임시 이름으로 쓴 뒤 바꿔서, 다른 Pod가 덜 써진 파일을 읽지 않게 함
            part = out / "cleaned" / f".{rid}.part.wav"
            sf.write(part, np.clip(other, -1, 1), 44100, subtype="PCM_16")
            os.replace(part, out / "cleaned" / f"{rid}.wav")
            sf.write(out / "crowd" / f"{rid}.flac", np.clip(crowd, -1, 1), 44100)
            row["crowd_ratio_db"], row["crowd_sec_frac"], row["crowd_peak_db"] = metrics(mix, crowd, sr)
            row["seconds_audio"] = round(n / sr, 1)
        except Exception as e:  # 한 곡 실패해도 다음 곡 진행
            row["status"] = f"fail: {e}"[:300]
        finally:
            for f in tmp.glob("*"):
                f.unlink()
        row["seconds_proc"] = round(time.time() - t0, 1)
        done[rid] = row
        print(f"[{row['status'][:4]}] {rid} ratio={row.get('crowd_ratio_db')} dB "
              f"frac={row.get('crowd_sec_frac')} ({row['seconds_proc']} s)", flush=True)
        with open(mpath, "w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=fields, extrasaction="ignore"); w.writeheader()
            w.writerows(done[k] for k in sorted(done))
    shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main(*sys.argv[1:4])
