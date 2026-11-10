#!/usr/bin/env bash
# AI-generated with Claude Code, 2026-10-13
# Runs inside the SGS GPU pod.  Sends every file in /data/input through
# /data/pipeline/audio_to_midi.sh and writes /data/output/<name>/.
# Songs that already have a transcription are skipped, so a preempted pod can
# simply be submitted again.
set -uo pipefail
# keep every download and install on the volume: the container's own disk is
# limited to 10 GiB and is lost when the pod ends
export UV_CACHE_DIR=/data/cache/uv UV_TOOL_DIR=/data/cache/uv-tools \
       UV_PYTHON_INSTALL_DIR=/data/cache/python HF_HOME=/data/cache/hf \
       TORCH_HOME=/data/cache/torch XDG_CACHE_HOME=/data/cache/xdg
mkdir -p /data/output /data/cache/xdg
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
failed=0
shopt -s nullglob
for audio in /data/input/*; do
  name=$(basename "${audio%.*}")
  if [[ -s "/data/output/$name/transcription.mid" ]]; then echo "skip    $name"; continue; fi
  started=$(date +%s)
  if bash /data/pipeline/audio_to_midi.sh "$audio" /data/output /data/model/model.safetensors cuda
  then status=ok; else status=FAILED; fi
  echo "$status  $(( $(date +%s) - started ))s  $name"
  if [[ $status == FAILED ]]; then failed=1; tail -n 20 "/data/output/$name"/*.log; fi
done
echo finished
exit $failed
