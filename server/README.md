# ROCKY server

HTTP API between the Android app and the GPU pipeline
(`ml/pipeline/unified.py` on the `ml/unified-pipeline` branch).

```
app ──upload──▶ API pod (CPU, always on) ──asks──▶ laptop agent ──creates──▶ GPU Pod: unified.py
                     │                                                        CPU Pod: publish_scores.py
                     └── reads manifest.json / progress.jsonl / scores/ on the shared volume
```

On SGS the team accounts may create Pods but not Roles/RoleBindings, so the API
pod cannot be given permission to create Pods. With `ROCKY_RUNNER=agent` (used by
`k8s/api-pod.yaml`) the API queues Pod requests and `agent/rocky_agent.py`, run on a
laptop logged in with kubectl, creates them, waits out the GPU quota, watches them,
reports the result through `/agent/*` and deletes them. Step-by-step deployment in
Korean: `DEPLOY_ko.md`.

The API pod has no GPU, so the 30-minute idle-GPU rule does not apply to it.
A GPU is used only while a song's GPU Pod runs. `ROCKY_PARALLEL` controls how
many songs can be in flight; the others wait in upload order. The current SGS
namespace has a one-GPU quota and the production API uses `ROCKY_PARALLEL=1`.

## API

| Method | Path | Result |
| --- | --- | --- |
| `GET` | `/health` | `{"ok": true}` |
| `POST` | `/jobs` | multipart: `file` (wav/mp3/flac/m4a/ogg), `requested` (e.g. `piano,guitar`), `title` → `{"id", "state"}` |
| `GET` | `/jobs/{id}` | `state` (`uploading`, `queued`, `running`, `publishing`, `cancelling`, `cancelled`, `complete`, `failed`), `queue_position`, `error`, and progress: `stage` (`SEPARATE`, `TRANSCRIBE`, `BEATS`, `ARRANGE`), `completed`, `total`, `fraction` (0–1), `eta_sec` |
| `POST` | `/jobs/{id}/cancel` | Idempotently request cancellation; returns `{"id", "state"}`. A queued song becomes `cancelled` immediately. An active song becomes `cancelling` until the agent confirms its Pod has been deleted, then becomes `cancelled`. Completed songs remain complete. |
| `GET` | `/jobs/{id}/result` | `full_band` and `instruments.<part>` with `pdf`, `midi`, `pages`; `original_parts`, `generated_parts` |
| `GET` | `/jobs/{id}/files/{path}` | one file listed in the result (nothing else on the volume) |

When `ROCKY_API_KEY` is set, every request except `/health` needs the header
`X-Rocky-Key`. Interactive docs: `/docs`.

Progress uses the app's four stages with the same weights as
`app/.../progress/JobProgress.kt` (0.10 / 0.75 / 0.05 / 0.10). During
transcription, `completed`/`total` are MuScriptor's 5-second chunks summed
over the four transcribed stems. `eta_sec` is null until the first chunk
finishes.

After a job is complete the server deletes its separated stems and the
uploaded audio (the volume has only a few GiB free). MIDI, TAB and PDF stay.
After cancellation it removes the partial run and uploaded audio once the
running Pod has stopped. The next queued song is then picked up by the worker.
The laptop agent must be connected to delete an active Pod. If it is offline,
the job stays `cancelling` until an agent reconnects (or the request times out).
Deploy the Android app, API code, and laptop agent together: older API versions
do not have `/jobs/{id}/cancel`, and older agents do not acknowledge Pod deletion
before the API advances the queue.

## Run on SGS

Prerequisites: the unified pipeline is set up on the volume
(`/data/pipeline`, `/data/rocky-unified/...`) as `ml/pipeline/README.md` describes.

```bash
# 1. Copy this folder to the volume (rocky-files pod from ml/pipeline/sgs/files-pod.yaml)
tar -C server -cf - rocky_server requirements.txt | kubectl exec -i rocky-files -- \
    bash -c 'mkdir -p /data/server && tar -C /data/server -xf -'

# 2. Once: permissions to create Jobs, and the API key
kubectl apply -f server/k8s/rbac.yaml
kubectl create secret generic rocky-api --from-literal=api-key=<long random text>

# 3. Start the API pod
kubectl apply -f server/k8s/api-pod.yaml
kubectl logs -f rocky-api

# 4. Try it from your laptop
kubectl port-forward pod/rocky-api 8000:8000
curl localhost:8000/health
```

For a phone on USB during development: `adb reverse tcp:8000 tcp:8000`, then
the app's server address `http://localhost:8000` reaches the API.

After changing the code, copy it again (step 1) and `kubectl delete pod rocky-api`;
`restartPolicy: Always` does not recreate a deleted bare pod, so apply step 3 again.
Unfinished jobs are queued again on start and `unified.py --resume` skips
finished stages.

## Run locally

```bash
pip install -r requirements-dev.txt
pytest                                   # 25 tests, no GPU or cluster needed
ROCKY_RUNNER=subprocess ROCKY_HOME=./local/app ROCKY_RUNS=./local/runs ROCKY_INPUTS=./local/input \
  ROCKY_MIDI_CMD="python /path/to/unified.py {audio} {run} --requested {requested} --resume --device cpu" \
  ROCKY_PDF_CMD="python /path/to/publish_scores.py {run}" \
  uvicorn rocky_server.app:app_from_env --factory --port 8000
```

`ROCKY_RUNNER=subprocess` runs the two commands directly instead of creating
Jobs. Settings are listed at the top of `rocky_server/app.py` and in `.env.example`.

## Not done yet

- A public HTTPS address for phones without USB (tunnel), see the project notes.
- Accounts on the server: jobs are not tied to a user; anyone with the key can read any job id.
