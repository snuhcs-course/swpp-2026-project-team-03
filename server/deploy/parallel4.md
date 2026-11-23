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

## End-to-end check on gpu22, 2026-11-23

An isolated test API Pod (label `app=rocky-api-test`, so the public tunnel's
`rocky-api` Service never routes to it; its own job store and run folders under
`/data/rocky-test`; the PR #48 server code; `ROCKY_ABANDON_SEC=0`) on ford took
uploads through `kubectl port-forward`. Pipeline on the volume: `unified.py`
sha256 `0cafc328…`, `publish_scores.py` `45f58d37…`. Four dev songs from the
team's dev list: Peanut Butter Sandwich (지소쿠리클럽), 고백 (델리스파이스,
323.5 s), A Sky Full Of Stars (Coldplay), Smells Like Teen Spirit (Nirvana).
Every song: requested `piano,drums,bass,guitar`, lineup
`piano,drums,bass,guitar,guitar2`, original empty.

| Run | Settings | Song | Wait | Start to complete | GPU stages | PDF stage | Files |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | PARALLEL=2, GPU Pod 4 CPU / 16Gi, threads unset, PDF 4 / 8Gi | Peanut | 0 s | 276 s | 250 s | ~35 s | 21/21 |
| A | same | 고백 | 0 s | 511 s | 469 s | ~56 s | 21/21 |
| B | PARALLEL=2, GPU Pod 2 / 8Gi, threads 2, PDF 2 / 8Gi | Peanut | 0 s | 272 s | 244 s | ~35 s | 21/21 |
| B | same | 고백 | 0 s | 507 s | 461 s | ~57 s | 21/21 |
| C | PARALLEL=4, the values in this document | Peanut | 0 s | 277 s | 244 s | ~41 s | 21/21 |
| C | same | 고백 | 0 s | 512 s | 465 s | ~51 s | 21/21 |
| C | same | Coldplay | 0 s | 503 s | 449 s | ~61 s | 21/21 |
| C | same | Nirvana (MIDI-GPT generated piano and guitar, 238 s) | 0 s | 573 s | 521 s | ~61 s | 21/21 |

"Files" counts the full band and each part (guitar, bass, piano, drums,
guitar_1, guitar_2) as PDF, MP3 and MIDI, listed by `/jobs/{id}/result` and
downloaded with nonzero size. All songs completed with the `alpha_three_arm`
guitar count; Pod events show no OOM, eviction or restart. In each run the GPU
Pods started within the same minute; run C finished all four songs 584 s after
the first upload started.

During run C a key change (`POST /jobs/{id}/transpositions/2` on a run B
result) started while three GPU Pods and one PDF Pod were running and completed
in about 43 s. Namespace `limits.cpu` then peaked at 15500m of 16 and
`limits.memory` at 49280Mi of 64Gi (always-on Pods plus the 1 CPU test API).

Not yet checked: the same run on gpu05, CPU throttling counters, repeated runs,
and the peak disk use while four songs separate at once.

## Disk on gpu22

BS-RoFormer separation writes float32 stereo WAVs (about 353 KB per second of
audio per file), and up to about fifteen of them exist for one song while it
separates. From the code, four songs separating at once can need about 5 GB on
the volume (an estimate; not measured). `/data` on gpu22 had 3.0 GB free on
2026-11-23; 11 GB of finished experiment data was removed before run C, leaving
14 GB free, and at least 11 GB stayed free from 4.5 minutes into run C. Keep at
least 6 GB free on `/data` before running four songs at once; when it is full,
the app's own uploads and runs on the same volume fail too.

## Deployment and rollback

Check that `/data` has at least 6 GB free (`df -h /data` in `rocky-files`).
Deploy server code that includes PR #48 first, then follow the checks in
`parallel2-gpu05.md` (no active jobs, save the current Pod manifest, `kubectl
replace --force -f` the workspace's manifest, check `/health` and the Pod's
environment). For gpu22 use `server/k8s/ws2/api-pod.yaml`, which keeps the
API-key Secret.

To go back to two songs, set `ROCKY_PARALLEL=2`, `ROCKY_MIDI_CPU=4`,
`ROCKY_MIDI_MEMORY=16Gi` and remove the three new settings (or use the manifests
from before this change), then recreate the Pod the same way.
