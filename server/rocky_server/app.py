"""ROCKY HTTP API for the Android app.

POST /jobs                upload a song and the instruments to play -> job id
GET  /jobs/{id}           state and progress (stage, chunks, percent, time left)
POST /jobs/{id}/cancel    stop a queued or active job
GET  /jobs/{id}/result    PDF and MIDI files of a finished job
GET  /jobs/{id}/files/... download one of those files
DELETE /jobs/{id}         delete the job and its files (a running job is cancelled first)
GET  /health              liveness check

Members and bands (SQLite at ROCKY_HOME/rocky.db; see accounts.py). Login returns a token
that later calls send as "Authorization: Bearer <token>":
POST /auth/signup, POST /auth/login, POST /auth/logout, GET /auth/taken?email=|nickname=
GET|PATCH /me             my profile (nickname, instruments)
PATCH /me/works/{work_id}  rename my score in every band I shared it to
GET  /me/works/{work_id}/shared  whether I shared that score to a band
GET|POST /bands           my bands / make a band;  POST /bands/join  join with an invite code
GET|PATCH /bands/{id}     band detail / rename (owner);  POST /bands/{id}/leave
POST /bands/{id}/scores   share a score;  PATCH /bands/{id}/scores/{sid}  rename it

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
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from .accounts import AccountError, Accounts, User
from .jobs import JobStore, Worker
from .lineup import APP_PARTS, LineupError, pipeline_args
from .progress import allowed_paths, result_files, run_progress
from .runners import make_runner

INSTRUMENTS = ("piano", "guitar", "bass", "drums")
AUDIO_EXT = (".wav", ".mp3", ".flac", ".m4a", ".ogg")
CHUNK = 1024 * 1024


def create_app(store: JobStore | None = None, runner=None, start_worker: bool = True,
               accounts: Accounts | None = None) -> FastAPI:
    store = store or JobStore(Path(os.environ.get("ROCKY_HOME", "/data/rocky-unified/app")),
                              Path(os.environ.get("ROCKY_RUNS", "/data/rocky-unified/runs")),
                              Path(os.environ.get("ROCKY_INPUTS", "/data/input/app")))
    runner = runner or make_runner(os.environ.get("ROCKY_RUNNER", "kubernetes"))
    worker = Worker(store, runner, int(os.environ.get("ROCKY_PARALLEL", "1")))
    accounts = accounts or Accounts(store.root / "rocky.db")
    api_key = os.environ.get("ROCKY_API_KEY", "")
    max_bytes = int(os.environ.get("ROCKY_MAX_UPLOAD_MB", "60")) * CHUNK
    transpose_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_app):
        if start_worker:
            worker.start()
        yield

    app = FastAPI(title="ROCKY API", version="1.0", lifespan=lifespan)
    app.state.store, app.state.worker, app.state.accounts = store, worker, accounts

    @app.exception_handler(AccountError)
    async def account_error(_request, exc: AccountError):
        return JSONResponse({"detail": exc.message, "field": exc.field}, status_code=exc.status)

    def check_key(x_rocky_key: str | None = Header(default=None)) -> None:
        if api_key and x_rocky_key != api_key:
            raise HTTPException(401, "missing or wrong X-Rocky-Key")

    def current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ").strip()
        user = accounts.user_for_token(token) if token else None
        if user is None:
            raise HTTPException(401, "login required")
        return user

    def find(job_id: str):
        job = store.get(job_id) if re.fullmatch(r"[0-9a-f]{12}", job_id) else None
        if job is None or store.is_deleted(job_id):
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
        if store.is_deleted(job.id):  # deleted while the file was still arriving
            store.purge(job.id)
            raise HTTPException(410, "job was deleted during upload")
        worker.notify()
        return {"id": job.id, "state": job.state}

    @app.get("/jobs/{job_id}", dependencies=[Depends(check_key)])
    def job_status(job_id: str) -> dict:
        job = find(job_id)
        body = {"id": job.id, "title": job.title, "requested": job.requested, "state": job.state,
                "queue_position": worker.queue_position(job.id), "error": job.error, "note": job.note}
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

    @app.delete("/jobs/{job_id}", dependencies=[Depends(check_key)])
    def delete_job(job_id: str) -> dict:
        find(job_id)
        if accounts.job_shared(job_id):  # band members still open it from here
            raise HTTPException(409, "the score is shared to a band")
        with transpose_lock:  # not while a key change is writing into the run folder
            outcome = worker.delete(job_id)
        if outcome is None:
            raise HTTPException(404, "no such job")
        return {"id": job_id, "deleted": outcome == "deleted", "pending": outcome == "pending"}

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

    def transposed_run(job_id: str, semitones: int) -> Path:
        if not -12 <= semitones <= 12:
            raise HTTPException(422, "semitones must be between -12 and 12")
        job = find(job_id)
        if job.state != "complete":
            raise HTTPException(409, f"job is {job.state}")
        return store.run_dir(job.id) if semitones == 0 else store.run_dir(job.id) / "transpositions" / f"{semitones:+d}"

    def transposed_result(job_id: str, semitones: int) -> dict:
        run = transposed_run(job_id, semitones)
        try:
            result = result_files(run)
            paths = allowed_paths(result)
            if any(Path(path).is_absolute() or ".." in Path(path).parts for path in paths):
                raise ValueError("invalid result path")
            if not all((run / path).is_file() for path in paths):
                raise FileNotFoundError("transposition is incomplete")
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(404, "transposed score is not ready") from None
        return {"id": job_id, "title": find(job_id).title, "semitones": semitones, **result}

    @app.post("/jobs/{job_id}/transpositions/{semitones}", dependencies=[Depends(check_key)])
    def make_transposition(job_id: str, semitones: int) -> dict:
        run = transposed_run(job_id, semitones)
        if semitones == 0:
            return transposed_result(job_id, semitones)
        with transpose_lock:
            try:
                return transposed_result(job_id, semitones)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
            render = getattr(runner, "run_transpose", None)
            if not callable(render):
                raise HTTPException(501, "transposition is not supported by this runner")
            try:
                render(f"{job_id}-{abs(semitones):02d}{'p' if semitones > 0 else 'm'}",
                       store.run_dir(job_id), run, semitones, store.log(job_id))
            except (OSError, ValueError, RuntimeError) as exc:
                raise HTTPException(422 if isinstance(exc, ValueError) else 500, str(exc)[:300]) from exc
            return transposed_result(job_id, semitones)

    @app.get("/jobs/{job_id}/transpositions/{semitones}/result", dependencies=[Depends(check_key)])
    def get_transposition(job_id: str, semitones: int) -> dict:
        return transposed_result(job_id, semitones)

    @app.get("/jobs/{job_id}/transpositions/{semitones}/files/{rel:path}", dependencies=[Depends(check_key)])
    def transposed_file(job_id: str, semitones: int, rel: str):
        run = transposed_run(job_id, semitones)
        result = transposed_result(job_id, semitones)
        if rel not in allowed_paths(result):
            raise HTTPException(404, "not a result file")
        media = {"pdf": "application/pdf", "mp3": "audio/mpeg"}.get(rel.rsplit(".", 1)[-1], "audio/midi")
        return FileResponse(run / rel, media_type=media, filename=Path(rel).name)

    # ---- members ----
    keyed = [Depends(check_key)]

    def session(user: User, token: str) -> dict:
        return {"token": token, "user": user.json()}

    @app.post("/auth/signup", status_code=201, dependencies=keyed)
    def sign_up(body: dict = Body(...)) -> dict:
        user, token = accounts.sign_up(str(body.get("email", "")), str(body.get("password", "")),
                                       str(body.get("nickname", "")), body.get("instruments") or [])
        return session(user, token)

    @app.post("/auth/login", dependencies=keyed)
    def login(body: dict = Body(...)) -> dict:
        found = accounts.login(str(body.get("email", "")), str(body.get("password", "")))
        if found is None:  # same answer for an unknown email and a wrong password
            raise HTTPException(401, "wrong email or password")
        return session(*found)

    @app.post("/auth/logout", dependencies=keyed)
    def logout(authorization: str | None = Header(default=None)) -> dict:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token:
            accounts.logout(token)
        return {"ok": True}

    @app.get("/auth/taken", dependencies=keyed)
    def taken(email: str = "", nickname: str = "", authorization: str | None = Header(default=None)) -> dict:
        if email:
            return {"taken": accounts.email_taken(email)}
        token = (authorization or "").removeprefix("Bearer ").strip()
        me = accounts.user_for_token(token) if token else None
        return {"taken": accounts.nickname_taken(nickname, me.id if me else None)}

    @app.get("/me", dependencies=keyed)
    def me(user: User = Depends(current_user)) -> dict:
        return user.json()

    @app.patch("/me", dependencies=keyed)
    def update_me(body: dict = Body(...), user: User = Depends(current_user)) -> dict:
        return accounts.update_profile(user, str(body.get("nickname", "")), body.get("instruments") or []).json()

    @app.patch("/me/works/{work_id}", dependencies=keyed)
    def rename_my_work(work_id: int, body: dict = Body(...), user: User = Depends(current_user)) -> dict:
        accounts.rename_my_work(user, work_id, str(body.get("title", "")))
        return {"ok": True}

    @app.get("/me/works/{work_id}/shared", dependencies=keyed)
    def work_shared(work_id: int, user: User = Depends(current_user)) -> dict:
        return {"shared": accounts.work_shared(user, work_id)}

    # ---- bands ----
    @app.get("/bands", dependencies=keyed)
    def my_bands(user: User = Depends(current_user)) -> list:
        return accounts.bands_of(user)

    @app.post("/bands", status_code=201, dependencies=keyed)
    def create_band(body: dict = Body(...), user: User = Depends(current_user)) -> dict:
        return accounts.create_band(user, str(body.get("name", "")), str(body.get("instrument", "")))

    @app.post("/bands/join", dependencies=keyed)
    def join_band(body: dict = Body(...), user: User = Depends(current_user)) -> dict:
        return accounts.join(user, str(body.get("code", "")), str(body.get("instrument", "")))

    @app.get("/bands/{band_id}", dependencies=keyed)
    def band_detail(band_id: int, user: User = Depends(current_user)) -> dict:
        return accounts.detail(user, band_id)

    @app.patch("/bands/{band_id}", dependencies=keyed)
    def rename_band(band_id: int, body: dict = Body(...), user: User = Depends(current_user)) -> dict:
        return accounts.rename_band(user, band_id, str(body.get("name", "")))

    @app.post("/bands/{band_id}/leave", dependencies=keyed)
    def leave_band(band_id: int, user: User = Depends(current_user)) -> dict:
        accounts.leave(user, band_id)
        return {"ok": True}

    @app.post("/bands/{band_id}/scores", dependencies=keyed)
    def share_score(band_id: int, body: dict = Body(...), user: User = Depends(current_user)) -> dict:
        if "work_id" not in body:
            raise HTTPException(422, "work_id is required")
        return {"created": accounts.share(user, band_id, body)}

    @app.patch("/bands/{band_id}/scores/{score_id}", dependencies=keyed)
    def rename_score(band_id: int, score_id: int, body: dict = Body(...),
                     user: User = Depends(current_user)) -> dict:
        accounts.rename_score(user, band_id, score_id, str(body.get("title", "")))
        return {"ok": True}

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
