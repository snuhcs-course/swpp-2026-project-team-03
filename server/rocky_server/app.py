"""ROCKY HTTP API for the Android app.

POST /jobs                upload a song and the instruments to play -> job id
GET  /jobs/{id}           state and progress (stage, chunks, percent, time left)
POST /jobs/{id}/cancel    stop a queued or active job
GET  /jobs/{id}/result    PDF and MIDI files of a finished job
GET  /jobs/{id}/files/... download one of those files
GET  /health              liveness check

Settings (environment variables):
  ROCKY_RUNNER      agent (SGS: a laptop agent creates the Pods), kubernetes (the API pod
                    creates them; needs RBAC) or subprocess (run the commands here)
  ROCKY_HOME        where job records live (default /data/rocky-unified/app)
  ROCKY_RUNS        where unified.py writes each job (default /data/rocky-unified/runs)
  ROCKY_INPUTS      where uploads are saved (default /data/input/app)
  ROCKY_API_KEY     if set, every request needs header X-Rocky-Key with this value
  ROCKY_MAX_UPLOAD_MB  upload size limit (default 60)
  ROCKY_PARALLEL    songs processed at once = GPUs usable at once (default 1)
"""

from __future__ import annotations

import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .jobs import JobStore, Worker
from .lineup import APP_PARTS, LineupError, pipeline_args
from .progress import allowed_paths, result_files, run_progress
from .runners import make_runner

INSTRUMENTS = ("piano", "guitar", "bass", "drums")
AUDIO_EXT = (".wav", ".mp3", ".flac", ".m4a", ".ogg")
CHUNK = 1024 * 1024


def create_app(store: JobStore | None = None, runner=None, start_worker: bool = True) -> FastAPI:
    store = store or JobStore(Path(os.environ.get("ROCKY_HOME", "/data/rocky-unified/app")),
                              Path(os.environ.get("ROCKY_RUNS", "/data/rocky-unified/runs")),
                              Path(os.environ.get("ROCKY_INPUTS", "/data/input/app")))
    runner = runner or make_runner(os.environ.get("ROCKY_RUNNER", "kubernetes"))
    worker = Worker(store, runner, int(os.environ.get("ROCKY_PARALLEL", "1")))
    api_key = os.environ.get("ROCKY_API_KEY", "")
    max_bytes = int(os.environ.get("ROCKY_MAX_UPLOAD_MB", "60")) * CHUNK

    @asynccontextmanager
    async def lifespan(_app):
        if start_worker:
            worker.start()
        yield

    app = FastAPI(title="ROCKY API", version="1.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker

    def check_key(x_rocky_key: str | None = Header(default=None)) -> None:
        if api_key and x_rocky_key != api_key:
            raise HTTPException(401, "missing or wrong X-Rocky-Key")

    def find(job_id: str):
        job = store.get(job_id) if re.fullmatch(r"[0-9a-f]{12}", job_id) else None
        if job is None:
            raise HTTPException(404, "no such job")
        return job

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/jobs", status_code=201, dependencies=[Depends(check_key)])
    async def create_job(file: UploadFile = File(...), requested: str = Form(""),
                         title: str = Form(""), original: str = Form(""), lineup: str = Form("")) -> dict:
        parts = [p.strip() for p in requested.split(",") if p.strip()]
        if len(parts) != len(set(parts)) or any(p not in INSTRUMENTS for p in parts):
            raise HTTPException(422, f"requested must be distinct names from {','.join(INSTRUMENTS)}")
        # lineup: our band in app part names (guitar2 = second guitar); falls back to `requested`.
        # original: what the user heard in the song, same names; empty = "I don't know".
        app_lineup = [p.strip() for p in lineup.split(",") if p.strip() in APP_PARTS] or parts
        orig = [p.strip() for p in original.split(",") if p.strip() in APP_PARTS]
        try:
            pipe_original, pipe_requested = pipeline_args(app_lineup, orig)
        except LineupError as exc:
            raise HTTPException(422, str(exc)) from exc
        ext = Path(file.filename or "").suffix.lower()
        if ext not in AUDIO_EXT:
            raise HTTPException(415, f"audio must be one of {' '.join(AUDIO_EXT)}")
        job = store.create(title.strip()[:120] or Path(file.filename or "song").stem, "", parts,
                           original=orig, lineup=app_lineup,
                           pipeline_original=pipe_original, pipeline_requested=pipe_requested)
        target = store.inputs / f"{job.id}{ext}"
        size = 0
        with target.open("wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    target.unlink(missing_ok=True)
                    store.path(job.id).unlink(missing_ok=True)
                    raise HTTPException(413, f"file is larger than {max_bytes // CHUNK} MB")
                out.write(chunk)
        if size == 0:
            target.unlink(missing_ok=True)
            store.path(job.id).unlink(missing_ok=True)
            raise HTTPException(422, "empty file")
        store.update(job, filename=target.name, state="queued")
        worker.notify()
        return {"id": job.id, "state": job.state}

    @app.get("/jobs/{job_id}", dependencies=[Depends(check_key)])
    def job_status(job_id: str) -> dict:
        job = find(job_id)
        body = {"id": job.id, "title": job.title, "requested": job.requested, "state": job.state,
                "queue_position": worker.queue_position(job.id), "error": job.error, "note": job.note,
                "reason": job.reason}
        if job.state == "queued":
            body.update(stage="SEPARATE", completed=0, total=1, fraction=0.0, eta_sec=None)
        elif job.state == "complete":
            body.update(stage="ARRANGE", completed=1, total=1, fraction=1.0, eta_sec=0)
        else:
            elapsed = time.time() - job.started_at if job.started_at else None
            body.update(run_progress(store.run_dir(job.id), elapsed))
        return body

    @app.post("/jobs/{job_id}/cancel", dependencies=[Depends(check_key)])
    def cancel_job(job_id: str) -> dict:
        find(job_id)
        try:
            state = worker.cancel(job_id)
        except NotImplementedError as exc:
            raise HTTPException(501, str(exc)) from exc
        return {"id": job_id, "state": state}

    @app.get("/jobs/{job_id}/result", dependencies=[Depends(check_key)])
    def job_result(job_id: str) -> dict:
        job = find(job_id)
        if job.state != "complete":
            raise HTTPException(409, f"job is {job.state}")
        return {"id": job.id, "title": job.title, **result_files(store.run_dir(job.id))}

    @app.get("/jobs/{job_id}/files/{rel:path}", dependencies=[Depends(check_key)])
    def job_file(job_id: str, rel: str):
        job = find(job_id)
        if job.state != "complete":
            raise HTTPException(409, f"job is {job.state}")
        run = store.run_dir(job.id)
        # Only files listed in the result can be downloaded (no other paths on the volume).
        if rel not in allowed_paths(result_files(run)):
            raise HTTPException(404, "not a result file")
        media = {"pdf": "application/pdf", "mp3": "audio/mpeg"}.get(rel.rsplit(".", 1)[-1], "audio/midi")
        return FileResponse(run / rel, media_type=media, filename=Path(rel).name)

    # ---- laptop agent (ROCKY_RUNNER=agent): server/agent/rocky_agent.py ----
    if hasattr(runner, "next_request"):
        @app.get("/agent/next", dependencies=[Depends(check_key)])
        def agent_next(agent: str):
            req = runner.next_request(agent[:80])
            return req if req is not None else Response(status_code=204)

        @app.post("/agent/requests/{rid}/heartbeat", dependencies=[Depends(check_key)])
        def agent_heartbeat(rid: str, body: dict = Body(...)) -> dict:
            result = runner.heartbeat(rid, str(body.get("agent", ""))[:80], body.get("note"))
            if result == "cancel":
                raise HTTPException(410, "job cancellation requested")
            if not result:
                raise HTTPException(409, "request is gone or taken by another agent")
            return {"ok": True}

        @app.post("/agent/requests/{rid}/done", dependencies=[Depends(check_key)])
        def agent_done(rid: str, body: dict = Body(...)) -> dict:
            if not runner.finish(rid, str(body.get("agent", ""))[:80], str(body.get("phase", "")),
                                 str(body.get("log", ""))):
                raise HTTPException(409, "request is gone or taken by another agent")
            return {"ok": True}

    return app


def app_from_env() -> FastAPI:
    return create_app()
