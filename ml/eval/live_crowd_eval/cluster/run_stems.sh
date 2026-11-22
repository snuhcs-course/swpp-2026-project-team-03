#!/bin/bash
# 청취 판정용: 원본 음원을 파이프라인과 같은 BS-RoFormer로 분리해서, 필요한 악기 stem만 FLAC으로 남김
# 결과: /data/live_eval/listen_stems/<id>_<악기>.flac → listen_stems.tgz
set -uo pipefail
E=/data/live_eval; O=$E/listen_stems; mkdir -p $O
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch XDG_CACHE_HOME=/data/cache/xdg
PY=/data/rocky-unified/.venv/bin/python
log() { echo "=== $(date '+%F %T') $*"; }
for pair in L01:bass L12:bass L04:guitar,bass P04:bass P05:piano P08:guitar L16:guitar; do
  id=${pair%%:*}; insts=${pair#*:}; tmp=$E/_sep_tmp/$id
  log "$id 분리 시작"
  $PY /data/pipeline/separate_bs_roformer.py $E/wav/$id.wav $tmp \
    --models-dir /data/bsrofo/models --lib-dir /data/bsrofo/pylib > $E/_sep_$id.log 2>&1 || { log "$id 실패"; continue; }
  for inst in ${insts//,/ }; do
    $PY -c "import soundfile as sf,sys; x,sr=sf.read(sys.argv[1]); sf.write(sys.argv[2],x,sr)" $tmp/$inst.wav $O/${id}_$inst.flac
  done
  rm -rf $tmp; log "$id 끝"
done
rm -rf $E/_sep_tmp
cd $E && tar czf listen_stems.tgz listen_stems
log "ALL DONE — listen_stems.tgz 만듦. Pod 지우기: k22 delete pod rocky-live-stems"
