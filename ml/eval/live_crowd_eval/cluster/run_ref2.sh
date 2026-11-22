#!/bin/bash
# 03·07 원곡 비교용: 원곡 R01(Seven Nation Army), B22(그대에게)를 앱과 같은 명령으로 채보 → out/R/<id>, ref2.tgz
set -uo pipefail
E=/data/live_eval
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch UV_CACHE_DIR=/data/cache/uv \
  UV_TOOL_DIR=/data/cache/uv-tools UV_PYTHON_INSTALL_DIR=/data/cache/python XDG_CACHE_HOME=/data/cache/xdg
log() { echo "=== $(date '+%F %T') $*"; }
for id in R01 B22; do
  out=$E/out/R/$id; mkdir -p $out; log "$id 원곡 채보 시작"
  /data/rocky-unified/.venv/bin/python -u /data/pipeline/unified.py $E/wav/$id.wav $out \
    --original unknown --requested piano,drums,bass,guitar \
    --bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib \
    --resume --no-publish > $E/out/_logs/${id}_R.log 2>&1
  log "$id 끝 (exit $?)"; rm -f $out/stems/*.wav
done
cd $E && tar czf ref2.tgz out/R/R01/stem_midi_gated out/R/B22/stem_midi_gated && ls -lh ref2.tgz
log "ALL DONE — Pod 지우기: k22 delete pod rocky-live-ref2"
