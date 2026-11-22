#!/bin/bash
# crowd 분리만 하는 두 번째 GPU Pod용 (본 실험 Pod와 동시에 실행).
# audio-separator의 의존성 diffq는 C 컴파일러가 있어야 설치되는데 이 이미지에는 없음.
# diffq는 Demucs 계열 모델에서만 쓰고 Mel-Band RoFormer에는 필요 없어서, 빼고 설치함.
set -uo pipefail
E=/data/live_eval; C=/data/envs/crowd
export UV_CACHE_DIR=/data/cache/uv UV_PYTHON_INSTALL_DIR=/data/cache/python UV_LINK_MODE=hardlink XDG_CACHE_HOME=/data/cache/xdg
log() { echo "=== $(date '+%F %T') $*"; }
if ! $C/bin/python -c "import audio_separator.separator" 2>/dev/null; then
  log "crowd 환경 설치 (diffq 제외)"
  rm -rf $C && uv venv --python 3.11 $C || exit 1
  uv pip install --python $C/bin/python "torch==2.5.1" imageio-ffmpeg soundfile "numpy>=2" \
    "beartype>=0.18.5,<0.19" "einops>=0.7" "julius>=0.2" "librosa>=0.10" ml_collections onnxruntime packaging \
    "pydub>=0.25" pyyaml "requests>=2" "resampy>=0.4" "rotary-embedding-torch>=0.6.1,<0.7" "samplerate==0.1.0" \
    "scipy>=1.13,<2" six tqdm || exit 1
  uv pip install --python $C/bin/python --no-deps audio-separator==0.48.0 || exit 1
  $C/bin/python -c "import audio_separator.separator.architectures.mdxc_separator, torch; print('crowd env ok, cuda', torch.cuda.is_available())" || exit 1
fi
FF=$($C/bin/python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())") && mkdir -p $C/ffbin && ln -sf "$FF" $C/ffbin/ffmpeg && export PATH=$C/ffbin:$PATH
log "crowd 분리 시작"
$C/bin/python -u $E/crowd_sep.py $E/wav $E/crowd /data/cache/audio-separator-models
log "crowd 분리 끝 — 이 Pod는 지워도 됨: k22 delete pod rocky-live-crowd"
