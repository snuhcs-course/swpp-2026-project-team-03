#!/bin/bash
# cleaned2(원본 - crowd)를 만들고 38곡을 다시 돌림(arm C). 결과: out/C/<id>, out/summary.tsv(arm=C)
set -uo pipefail
E=/data/live_eval
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch UV_CACHE_DIR=/data/cache/uv \
  UV_TOOL_DIR=/data/cache/uv-tools UV_PYTHON_INSTALL_DIR=/data/cache/python XDG_CACHE_HOME=/data/cache/xdg
REQUESTED=${REQUESTED:-piano,drums,bass,guitar}
log() { echo "=== $(date '+%F %T') $*"; }
log "cleaned2 만들기"
/data/envs/crowd/bin/python -u $E/make_clean2.py $E || { log "cleaned2 실패"; exit 1; }
while read -r id; do
  [ -n "$id" ] || continue
  in=$E/crowd/cleaned2/$id.wav; out=$E/out/C/$id
  grep -qP "^$id\tC\t\d+\t0$" $E/out/summary.tsv && { log "$id C 이미 끝남"; continue; }
  mkdir -p "$out"; t0=$(date +%s); log "$id C 시작"
  /data/rocky-unified/.venv/bin/python -u /data/pipeline/unified.py "$in" "$out" \
    --original unknown --requested "$REQUESTED" \
    --bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib \
    --resume --no-publish > $E/out/_logs/${id}_C.log 2>&1
  rc=$?; t1=$(date +%s); rm -f "$out"/stems/*.wav
  printf '%s\t%s\t%s\t%s\n' "$id" C "$((t1-t0))" "$rc" >> $E/out/summary.tsv
  log "$id C 끝 $((t1-t0)) s (exit $rc)"
done < $E/pipeline_ids.txt
cd $E && tar czf out_C.tgz out/C out/summary.tsv crowd/clean2_check.csv
log "ALL DONE — out_C.tgz 만듦. Pod 지우기: k22 delete pod rocky-live-clean2"
