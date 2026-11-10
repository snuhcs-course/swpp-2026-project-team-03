#!/usr/bin/env bash
# Transcribe every available MulTTiPop segment with MuScriptor, then collapse
# the reference and the prediction into keyboard/guitar/bass/drums.
# Usage: ./run_muscriptor.sh [small|medium|large]
# Reads   data/audio/multtipop/<id>.wav (paths from audio_manifest.csv)
# Writes  outputs/multtipop/<id>/muscriptor_<model>.mid and *_collapsed.mid
set -euo pipefail

model=${1:-medium}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_root=$(cd -- "$script_dir/../../.." && pwd)
cd "$project_root"
collapse=(uvx --quiet --with pretty_midi --with "setuptools<81" python "$script_dir/collapse_midi.py")

# id, audio_path, reference_midi are simple tokens (no commas or spaces)
tail -n +2 "$script_dir/audio_manifest.csv" | tr -d '\r' | awk -F, '{print $1, $(NF-1), $NF}' |
while read -r id audio reference; do
  if [[ ! -f "$audio" ]]; then
    echo "skip $id: $audio not found"
    continue
  fi
  out_dir="outputs/multtipop/$id"
  mkdir -p "$out_dir"
  echo "=== $id ==="
  if [[ -f "$out_dir/muscriptor_${model}.mid" ]]; then
    echo "transcription exists, reusing it"
  else
  # Tempo detection must stay off: when it finds a tempo, MuScriptor delays
  # every note by a constant (0.8 s measured) and onset scores drop to ~0.
  { time uvx --python 3.13 muscriptor transcribe "$audio" --model "$model" \
      --output "$out_dir/muscriptor_${model}.mid" --format midi --detect-tempo false; \
  } < /dev/null 2>&1 | tee "$out_dir/muscriptor_${model}.log"
  fi
  "${collapse[@]}" "$reference" "$out_dir/reference_collapsed.mid" \
    --drop-vocal-tracks --report "$out_dir/reference_collapse_report.json"
  "${collapse[@]}" "$out_dir/muscriptor_${model}.mid" "$out_dir/muscriptor_${model}_collapsed.mid" \
    --report "$out_dir/muscriptor_${model}_collapse_report.json"
done
