# gpu05 two-song deployment

The gpu05/ferrari API uses `ROCKY_RUNNER=kubernetes` and `ROCKY_PARALLEL=2`.
Each active song gets one GPU Pod limited to 4 CPU, 16Gi (`ROCKY_MIDI_CPU`,
`ROCKY_MIDI_MEMORY` in the gpu05 manifests; the code default is 8 CPU / 32Gi), and
one GPU. Recreate the API Pod from the manifest when deploying this code. The GPU
Pod is followed by a CPU publication Pod. A third song remains queued until a
worker finishes. The API creates and watches Pods directly, without a laptop
agent. All work Pods are pinned to ferrari because `muscriptor-data` is there.

The runner explicitly requests zero ephemeral storage. This is needed because
the workspace's ephemeral-storage *request* quota is zero and admission otherwise
applies a nonzero default. The Pod status is read through the ordinary Pod API;
the default service account cannot access `pods/status` in the tested deployment.

## Deployment and checks

Before recreating `rocky-api`, check that no user job is `queued`, `running`,
`publishing`, or `cancelling`, and save the current Pod manifest and deployed
`runners.py`. A bare Pod's environment cannot be changed in place. The
`server/k8s/api-pod.yaml` manifest is for **gpu05 only**; use `kubectl replace
--force -f server/k8s/api-pod.yaml` to recreate it after the corresponding
server code is deployed. Check `/health`, `ROCKY_RUNNER`, `ROCKY_PARALLEL`, Pod
creation permission, and the GPU Pod resource spec. Do not copy this branch's
entire server package over an older runtime without checking its other API and
pipeline contracts.

For a quick one-worker rollback that keeps direct in-cluster Pod management and
the 4 CPU / 16Gi size, wait for active jobs to finish and run:

```sh
kubectl -n ws-qt1ja5byz6220 replace --force -f server/k8s/api-pod-single.yaml
```

Restore a saved pre-change runner and Pod manifest only if a full return to the
old laptop-agent mode is required; that mode needs a connected agent to process
new jobs.

## Verification on 2026-11-21

On gpu05, an isolated API with the same runner settings accepted two HTTP
uploads of one allowed development recording with different requested lineups.
Both GPU Pods started at 12:16:29 UTC on ferrari, used distinct GPUs, and had
4 CPU / 16Gi limits. Both jobs completed the GPU and CPU publication stages;
`GET /jobs/{id}/result` returned HTTP 200, and the result bundles passed
`publication_ready()`. The full-band PDF, MP3, and MIDI files were present for
both jobs. The jobs took 398.2 and 426.4 seconds from claim to completion.
During concurrent GPU execution, the namespace used 2/4 GPUs, 14.5/16 CPU,
and 43/64Gi memory, including a temporary 0.5 CPU / 1Gi uploader Pod. That
Pod was removed. This test establishes two-request API-to-publication operation;
it is not a paired one-worker speed benchmark or Android UI UAT.

The running gpu05 API was then recreated with the new manifest. Its `/health`
returned HTTP 200 and its environment reported `kubernetes` and `2`. The
deployed runner resource spec reported 4 CPU / 16Gi / one GPU and zero
ephemeral-storage request.

## gpu22/ford

On 2026-11-22 the public gpu22 API was recreated with `ROCKY_PARALLEL=2`,
`ROCKY_MIDI_CPU=4`, and `ROCKY_MIDI_MEMORY=16Gi`, with no active jobs. Its quota is
16 CPU / 64Gi / 4 GPUs. `/health` returned HTTP 200 in the Pod and through the
`rocky-api` Service. The two-upload API → GPU → PDF check has not been run on gpu22.
Use `server/k8s/ws2/api-pod.yaml` to recreate this Pod, because it keeps the API-key Secret.
