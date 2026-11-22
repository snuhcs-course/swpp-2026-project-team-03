#!/bin/bash
# 05 원곡 비교용: 스튜디오 원곡 B13(여수 밤바다)을 앱과 같은 명령으로 채보 → out/R/B13, 결과 묶음 ref_B13.tgz
set -uo pipefail
E=/data/live_eval
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch UV_CACHE_DIR=/data/cache/uv \
  UV_TOOL_DIR=/data/cache/uv-tools UV_PYTHON_INSTALL_DIR=/data/cache/python XDG_CACHE_HOME=/data/cache/xdg
log() { echo "=== $(date '+%F %T') $*"; }
out=$E/out/R/B13; mkdir -p $out; log "B13 원곡 채보 시작"
/data/rocky-unified/.venv/bin/python -u /data/pipeline/unified.py $E/wav/B13.wav $out \
  --original unknown --requested piano,drums,bass,guitar \
  --bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib \
  --resume --no-publish > $E/out/_logs/B13_R.log 2>&1
rc=$?; log "B13 끝 (exit $rc)"
/data/rocky-unified/.venv/bin/python -c "import soundfile as sf; x,sr=sf.read('$out/stems/bass.wav'); sf.write('$out/bass_stem.flac',x,sr,subtype='PCM_24')"
rm -f $out/stems/*.wav
cd $E && tar czf ref_B13.tgz out/R/B13/stem_midi_gated out/R/B13/note_gate.json out/R/B13/bass_stem.flac && ls -lh ref_B13.tgz
log "ALL DONE — Pod 지우기: k22 delete pod rocky-live-ref"
