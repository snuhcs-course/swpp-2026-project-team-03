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

For Android Emulator verification of alphaTab, cancellation, and key changes,
see `EMULATOR_TEST_ko.md`.

The API pod has no GPU, so the 30-minute idle-GPU rule does not apply to it.
A GPU is used only while a song's GPU Pod runs. `ROCKY_PARALLEL` controls how
many songs can be in flight; the others wait in upload order. The current SGS
namespace has a one-GPU quota and the production API uses `ROCKY_PARALLEL=1`.

## API

| Method | Path | Result |
| --- | --- | --- |
| `GET` | `/health` | `{"ok": true}` |
| `POST` | `/jobs` | multipart: `file` (wav/mp3/flac/m4a/ogg), `requested` (e.g. `piano,guitar`), `title` → `{"id", "state"}` |
| `GET` | `/jobs/{id}` | `state` (`uploading`, `queued`, `running`, `publishing`, `cancelling`, `cancelled`, `complete`, `failed`), `queue_position`, `error`, `reason` (set only when the pipeline refused the input: `too_short`, `silent`, `not_band_audio`; `state` is then `failed` and `error` is a Korean message for the user), and progress: `stage` (`SEPARATE`, `TRANSCRIBE`, `BEATS`, `ARRANGE`), `completed`, `total`, `fraction` (0–1), `eta_sec` |
| `GET` | `/jobs/{id}` (failed) | Every other failure also sets `error_code` (`pdf_network`, `timeout`, `no_agent`, `pipeline_error`, `upload_interrupted`), `message` (Korean, for the user: what happened, how long to wait, what a retry will redo), `retryable`, `retry_after_sec` (`null`: right away) and `retry_from` (`pdf`: only the PDF stage runs again; `gpu`: `unified.py --resume` continues from the stage that stopped). `error` stays the developer's text. |
| `POST` | `/jobs/{id}/retry` | Run a failed song again under the same id → `{"id", "state": "queued", "retry_from", "queue_position"}`. `409` if the song did not fail, its input was refused (`reason`), or `retryable` is false; `410` if the uploaded audio is gone. |
| `POST` | `/jobs/{id}/cancel` | Idempotently request cancellation; returns `{"id", "state"}`. A queued song, or a song whose Pod request was never claimed by an agent, becomes `cancelled` immediately. If an agent has claimed the request, it remains `cancelling` until the agent confirms Pod deletion. Completed songs remain complete. |
| `GET` | `/jobs/{id}/result` | `full_band` and `instruments.<part>` with `pdf`, `midi`, `pages`; `original_parts`, `generated_parts`, `faint_parts` (parts the user said are in the song but whose stem barely sounds; the score may be empty or inaccurate) |
| `GET` | `/jobs/{id}/files/{path}` | one file listed in the result (nothing else on the volume) |
| `POST` | `/jobs/{id}/transpositions/{semitones}` | Request an absolute offset from the original key (`-12` through `12`). A new render returns `202` with `state: queued` or `running`; a cached render and zero offset return the result immediately. |
| `GET` | `/jobs/{id}/transpositions/{semitones}` | Poll the requested variant: `queued`, `running`, `failed` (with `error`), or `complete` (with the band/part result). A variant that was never requested returns `404`. |
| `GET` | `/jobs/{id}/transpositions/{semitones}/result` | Read an already rendered offset. |
| `GET` | `/jobs/{id}/transpositions/{semitones}/files/{path}` | Download a PDF, MIDI or MP3 from that offset. |
| `DELETE` | `/jobs/{id}` | Deletes the job record, upload, run folder, result files and key changes → `{"id", "deleted", "pending"}`. A queued song is removed at once. A running song is cancelled the same way as `POST /jobs/{id}/cancel` and removed when its Pod has stopped (`pending: true`). A job shared to a band is not deleted (`409`), because band members open it from the server. |

Key changes run in a CPU Pod. `transpose_scores.py` shifts pitched MIDI notes and
the guitar/bass GP5 notes; drum hits and timing stay fixed. If an open low string
cannot sound the requested lower pitch on the original tuning, its GP5 track is
retuned by the same interval so the TAB remains playable. The script then calls
the existing `publish_scores.py` to regenerate all band and part PDFs/MP3s.
Original files stay intact under the completed run; variants are under
`transpositions/{+n|-n}`. The app downloads a complete variant before making it
active in its private score folder. Rendering needs the laptop agent, the
completed run on the shared volume, and the same CPU renderer dependencies as
normal score publishing.
In the Android result screen, the four key buttons change a pending offset;
only the Apply button sends a request. For example, three quick `-2` taps
select `-6` and produce one render when applied, rather than rendering `-2`,
`-4`, and `-6` in sequence.
The POST does not hold the HTTP connection while the agent or CPU Pod is slow.
Different songs can render concurrently; variants of the same song render one
at a time. Deleting a song while its variant is still rendering returns `409`.
If a client stops polling, the server render continues; retry the same POST to
rejoin that render or restart it after a failure. A server restart loses the
in-memory request status, so retry the POST to resume an unfinished variant.

### Members and bands

Members, bands and shared scores are in one SQLite file, `$ROCKY_HOME/rocky.db`
(`rocky_server/accounts.py`), on the same volume as the job records, so nothing else has to run.
Sign-up and login return a `token`; the calls marked 🔒 need `Authorization: Bearer <token>`.
Errors come as `{"detail": "<message for the app>", "field": "email" | "nickname" | "code" | …}`.

| Method | Path | Result |
| --- | --- | --- |
| `POST` | `/auth/signup` | `{email, password, nickname, instruments}` → `{token, user}`; `409` + `field` if the email or nickname is taken |
| `POST` | `/auth/login` | `{email, password}` → `{token, user}`; `401` for an unknown email or a wrong password (same answer) |
| `POST` | `/auth/logout` | ends this token's session |
| `GET` | `/auth/taken?email=…` or `?nickname=…` | `{taken}` (with a token, my own nickname is not taken) |
| `GET` / `PATCH` | `/me` 🔒 | my profile / change `{nickname, instruments}` |
| `PATCH` | `/me/works/{work_id}` 🔒 | `{title}`: rename my score in every band I shared it to |
| `GET` | `/me/works/{work_id}/shared` 🔒 | `{shared}` |
| `GET` / `POST` | `/bands` 🔒 | my bands with member and score counts / make a band `{name, instrument}` |
| `POST` | `/bands/join` 🔒 | `{code, instrument}` → the band |
| `GET` / `PATCH` | `/bands/{id}` 🔒 | members and shared scores (members only) / rename `{name}` (owner only) |
| `POST` | `/bands/{id}/leave` 🔒 | the earliest member becomes owner; the band is deleted when the last member leaves |
| `POST` | `/bands/{id}/scores` 🔒 | share `{work_id, job_id, title, instruments, date, original}` → `{created}` |
| `PATCH` | `/bands/{id}/scores/{sid}` 🔒 | `{title}` (the sharer or the owner) |

The database starts with the demo band `BAND33` (three members who cannot log in, and the app's built-in demo song).
Passwords are stored as PBKDF2-SHA256 hashes and tokens as SHA-256 hashes.

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
- Jobs are not tied to a user: anyone with the key can read a job id (band members need this to open shared scores).
- Email verification: the app still shows the code on screen instead of sending a mail.
- The address is plain HTTP, so passwords travel unencrypted until there is an HTTPS address.
