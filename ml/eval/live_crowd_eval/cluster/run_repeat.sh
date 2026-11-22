#!/bin/bash
# 같은 원본을 한 번 더 돌려(A2) 파이프라인 자체의 실행 간 흔들림을 잼 (gpu22 Pod 안에서 실행)
# 명령은 run_all.sh의 A와 완전히 같음. 결과: /data/live_eval/out/A2/<id>, 시간: out/summary.tsv (arm=A2)
set -uo pipefail
E=/data/live_eval
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch UV_CACHE_DIR=/data/cache/uv \
  UV_TOOL_DIR=/data/cache/uv-tools UV_PYTHON_INSTALL_DIR=/data/cache/python XDG_CACHE_HOME=/data/cache/xdg
REQUESTED=${REQUESTED:-piano,drums,bass,guitar}
log() { echo "=== $(date '+%F %T') $*"; }
for id in ${REPEAT_IDS:-L17 S04 S07 L01 L12}; do
  in=$E/wav/$id.wav; out=$E/out/A2/$id
  grep -qP "^$id\tA2\t\d+\t0$" $E/out/summary.tsv && { log "$id A2 이미 끝남"; continue; }
  mkdir -p "$out"; t0=$(date +%s); log "$id A2 시작"
  /data/rocky-unified/.venv/bin/python -u /data/pipeline/unified.py "$in" "$out" \
    --original unknown --requested "$REQUESTED" \
    --bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib \
    --resume --no-publish > $E/out/_logs/${id}_A2.log 2>&1
  rc=$?; t1=$(date +%s); rm -f "$out"/stems/*.wav
  printf '%s\t%s\t%s\t%s\n' "$id" A2 "$((t1-t0))" "$rc" >> $E/out/summary.tsv
  log "$id A2 끝 $((t1-t0)) s (exit $rc)"
done
cd $E && tar czf out_A2.tgz out/A2 out/summary.tsv
log "ALL DONE — out_A2.tgz 만듦. Pod 지우기: k22 delete pod rocky-live-repeat"
