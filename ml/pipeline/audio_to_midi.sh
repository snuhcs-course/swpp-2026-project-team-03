#!/usr/bin/env bash
# AI-generated with Claude Code, 2026-10-13
# Audio -> MIDI in one step: remove vocals with Demucs, then transcribe the
# vocal-free mix with MuScriptor.
#
# Usage: ./audio_to_midi.sh INPUT_AUDIO [OUTPUT_DIR] [MODEL] [DEVICE]
#   OUTPUT_DIR  default outputs/pipeline; results go to OUTPUT_DIR/<input name>/
#   MODEL       small | medium (default) | large | path to a .safetensors file
#   DEVICE      auto (default) | cpu | cuda.  On a Mac use cpu for large: on MPS
#               the large model produces garbage.
# Writes stems/{vocals,drums,bass,other,no_vocals}.wav, transcription.mid and
# transcription.log.  Steps whose output already exists are skipped.
set -euo pipefail

input=$1
out_root=${2:-outputs/pipeline}
model=${3:-medium}
device=${4:-auto}
here=$(cd "$(dirname "$0")" && pwd)
name=$(basename "${input%.*}")
out="$out_root/$name"
mkdir -p "$out"

if [[ ! -s "$out/stems/no_vocals.wav" ]]; then
  echo "[1/2] Demucs: removing vocals from $name"
  uvx --quiet --python 3.11 --with demucs --with soundfile --with "torch<2.6" --with "torchaudio<2.6" \
    python "$here/separate_stems.py" "$input" "$out/stems" --model htdemucs --no-vocals-mix \
    > "$out/demucs.log" 2>&1
else
  echo "[1/2] Demucs: reusing $out/stems/no_vocals.wav"
fi

echo "[2/2] MuScriptor ($model): transcribing"
uvx --python 3.13 muscriptor transcribe "$out/stems/no_vocals.wav" --model "$model" --device "$device" \
  --output "$out/transcription.mid" --format midi --detect-tempo false \
  < /dev/null > "$out/transcription.log" 2>&1
echo "EOS warnings: $(grep -c 'did not emit EOS' "$out/transcription.log" || true)"
echo "MIDI: $out/transcription.mid"

# Later stages (beat alignment, arrangement, part generation) go here.  Read
# "$out/transcription.mid" and write the result into "$out".
