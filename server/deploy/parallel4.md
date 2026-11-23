# Four songs per workspace

Both manifests (`server/k8s/api-pod.yaml` for gpu05/ferrari and
`server/k8s/ws2/api-pod.yaml` for gpu22/ford) run up to four songs at once, one
per GPU in the workspace quota:

| Setting | Value | Code default |
| --- | --- | --- |
| `ROCKY_PARALLEL` | 4 | 1 |
| `ROCKY_MIDI_CPU` / `ROCKY_MIDI_MEMORY` (GPU Pod) | 2 / 8Gi | 4 / 16Gi |
| `ROCKY_MIDI_THREADS` (GPU Pod `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`) | 2 | unset |
| `ROCKY_PDF_CPU` / `ROCKY_PDF_MEMORY` (PDF and key-change Pods) | 2 / 8Gi | 4 / 8Gi |

These need the server code from PR #48 (`ROCKY_MIDI_THREADS`, `ROCKY_PDF_*`).
An older `/data/server` ignores those three settings and would start 4 CPU PDF
Pods, which then wait for quota.

## Quota

Each workspace has 4 GPUs, 16 CPU and 64Gi of limits (`kubectl describe resourcequota`,
2026-11-23). The always-on Pods use 6 CPU / 10Gi on gpu05 (`rocky-api`,
`rocky-files`, `rocky-work-files`) and 4.5 CPU / about 6.1Gi on gpu22. With four
songs, each in its GPU or PDF stage, work Pods use 8 CPU / 32Gi: 14 CPU on gpu05
and 12.5 CPU on gpu22. A key-change Pod (2 CPU / 8Gi) still fits. When a Pod
does not fit, the runner waits and retries instead of failing.

The GPUs are on shared nodes. On 2026-11-23 ferrari had 4 of its 7 GPUs allocated
to other namespaces, so gpu05 could start only three songs at that time; the
fourth waits for a GPU. ford's 4 GPUs were free.

## Measurements on gpu05, 2026-11-23

GPU stage: the same Pod script as Jaewook's 11/21 resource probes (`unified.py
--requested guitar1 --no-publish`, `OMP_NUM_THREADS=2`, output on an emptyDir),
`unified.py` sha256 `0cafc328…`. Peak memory is the cgroup `memory.peak`.

| Pod limits | Song | Time | Peak memory | OOM |
| --- | --- | --- | --- | --- |
| 4 CPU / 16Gi | `domestic_2/1ifkM7…wav` | 235 s | 3.29 GB | 0 |
| 3 CPU / 8Gi | same | 234 s | 3.30 GB | 0 |
| 2 CPU / 8Gi | same | 234 s | 3.31 GB | 0 |
| 2 CPU / 8Gi, three Pods started together | same | 236 / 236 / 235 s | about 3.3 GB each | 0 |
| 2 CPU / 8Gi | largest WAV in the set, 323.5 s audio | 446 s | 3.72 GB | 0 |

PDF stage: the PDF Pod's image and script (`.deb` install, `publish_scores.py`
sha256 `45f58d37…`) on a copy of app run `6a5df9832d1f`:

| Pod limits | Time | Peak memory | PDFs |
| --- | --- | --- | --- |
| 4 CPU / 8Gi | 32 s | 0.84 GB | 7 |
| 2 CPU / 8Gi | 34 s | 0.82 GB | 7 |

Not yet checked: four songs through the API from upload to PDF, and gpu22's disk
use with four songs' temporary stems at once (`/data` was 93% full on 2026-11-23).

## Deployment and rollback

Deploy server code that includes PR #48 first, then follow the checks in
`parallel2-gpu05.md` (no active jobs, save the current Pod manifest, `kubectl
replace --force -f` the workspace's manifest, check `/health` and the Pod's
environment). For gpu22 use `server/k8s/ws2/api-pod.yaml`, which keeps the
API-key Secret.

To go back to two songs, set `ROCKY_PARALLEL=2`, `ROCKY_MIDI_CPU=4`,
`ROCKY_MIDI_MEMORY=16Gi` and remove the three new settings (or use the manifests
from before this change), then recreate the Pod the same way.
