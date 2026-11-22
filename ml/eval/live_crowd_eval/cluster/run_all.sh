#!/bin/bash
# ROCKY 라이브 입력 전처리 실험 (gpu22 Pod 안에서 실행)
#  1단계: /data/envs/crowd 환경 설치 (처음 한 번)
#  2단계: wav 84개 전부 Mel-Band RoFormer Crowd → cleaned wav + crowd 판정 점수
#  3단계: pipeline_ids.txt의 곡(L·S·P 38곡)을 앱 서버와 같은 명령으로 unified.py 실행
#         A = 원본, B = cleaned. 곡마다 A → B 순서
# 결과: /data/live_eval/{crowd,out}/  진행 로그: /data/live_eval/run.log
# 기존 앱 파일(/data/rocky-unified, /data/pipeline 등)은 읽기만 하고 바꾸지 않음
set -uo pipefail
E=/data/live_eval
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch UV_CACHE_DIR=/data/cache/uv \
  UV_TOOL_DIR=/data/cache/uv-tools UV_PYTHON_INSTALL_DIR=/data/cache/python XDG_CACHE_HOME=/data/cache/xdg \
  UV_LINK_MODE=hardlink
REQUESTED=${REQUESTED:-piano,drums,bass,guitar}
log() { echo "=== $(date '+%F %T') $*"; }
df -h /data | tail -1
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# ---- 1단계: crowd 환경 (앱 venv와 분리)
C=/data/envs/crowd
if [ ! -x $C/bin/python ] || ! $C/bin/python -c "import audio_separator" 2>/dev/null; then
  log "crowd 환경 설치"
  TV=$(/data/rocky-unified/.venv/bin/python -c "import torch;print(torch.__version__.split('+')[0])")
  log "앱 파이프라인과 같은 torch $TV 사용"
  uv venv --python 3.11 $C && \
  uv pip install --python $C/bin/python "torch==$TV" audio-separator==0.48.0 imageio-ffmpeg soundfile numpy \
    || log "crowd 환경 설치 실패 → 2단계 건너뜀"
fi
# audio-separator는 ffmpeg 실행 파일이 PATH에 있어야 시작됨 → pip로 받은 ffmpeg를 연결
FF=$($C/bin/python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null) && \
  mkdir -p $C/ffbin && ln -sf "$FF" $C/ffbin/ffmpeg && export PATH=$C/ffbin:$PATH

# ---- 2단계: crowd 분리
log "2단계 crowd 분리 시작"
$C/bin/python -u $E/crowd_sep.py $E/wav $E/crowd /data/cache/audio-separator-models || log "2단계 실패 (3단계 A는 계속)"
log "2단계 끝"

# ---- 3단계: 파이프라인 A/B
mkdir -p $E/out/_logs
[ -f $E/out/summary.tsv ] || printf 'id\tarm\tseconds\texit\n' > $E/out/summary.tsv
while read -r id; do
  [ -n "$id" ] || continue
  for arm in A B; do
    if [ $arm = A ]; then in=$E/wav/$id.wav; else in=$E/crowd/cleaned/$id.wav; fi
    out=$E/out/$arm/$id
    [ -f "$in" ] || { log "$id $arm 입력 없음, 건너뜀"; continue; }
    grep -qP "^$id\t$arm\t\d+\t0$" $E/out/summary.tsv && { log "$id $arm 이미 끝남"; continue; }
    mkdir -p "$out"; t0=$(date +%s); log "$id $arm 시작"
    /data/rocky-unified/.venv/bin/python -u /data/pipeline/unified.py "$in" "$out" \
      --original unknown --requested "$REQUESTED" \
      --bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib \
      --resume --no-publish > $E/out/_logs/${id}_$arm.log 2>&1
    rc=$?; t1=$(date +%s)
    rm -f "$out"/stems/*.wav   # stem wav(곡당 수백 MB)는 지움, MIDI·박·로그는 남김
    printf '%s\t%s\t%s\t%s\n' "$id" "$arm" "$((t1-t0))" "$rc" >> $E/out/summary.tsv
    log "$id $arm 끝 $((t1-t0)) s (exit $rc)"; df -h /data | tail -1
  done
done < $E/pipeline_ids.txt
log "ALL DONE — 이제 Pod를 지워서 GPU를 돌려줘"
