# Historical SGS manifests

These files document the older SGS workflow. They are retained for reference
only. Do not apply the historical Job or PVC manifests for a new course run.

Use the active `../pod.yaml`, `../unified-pod.example.yaml`,
`../score-pdf-pod.example.yaml`, or `../files-pod.yaml` instead. Each active
manifest is a Pod pinned to `ferrari` and mounts the existing PVC at `/data`.
The older `run_all.sh` runs the Demucs/MuScriptor-only path, not the current
BS-RoFormer unified pipeline.
