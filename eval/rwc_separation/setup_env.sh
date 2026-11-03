#!/bin/bash
# Two Python environments on the volume (run once, in the CPU pod):
#   /data/envs/sep  Python 3.11: Demucs (torch<2.6, which the published checkpoints need) + BS-RoFormer
#   /data/envs/mus  Python 3.13: MuScriptor 0.4.0 + scoring (same versions as /data/rwc-eval on the team volume)
set -euo pipefail
export UV_CACHE_DIR=/data/cache/uv UV_PYTHON_INSTALL_DIR=/data/cache/python UV_LINK_MODE=hardlink
mkdir -p /data/envs
[ -x /data/envs/sep/bin/python ] || uv venv --python 3.11 /data/envs/sep
uv pip install --python /data/envs/sep/bin/python demucs soundfile "torch<2.6" "torchaudio<2.6" bs-roformer-infer==0.1.5
[ -x /data/envs/mus/bin/python ] || uv venv --python 3.13 /data/envs/mus
uv pip install --python /data/envs/mus/bin/python muscriptor==0.4.0 pretty_midi==0.2.11.post0 mir_eval==0.8.2 remotezip==0.12.6
/data/envs/sep/bin/python -c "import demucs, bs_roformer.inference, torch; print('sep ok, torch', torch.__version__)"
/data/envs/mus/bin/python -c "import muscriptor, mir_eval, remotezip, torch; print('mus ok, torch', torch.__version__)"
df -h /data
