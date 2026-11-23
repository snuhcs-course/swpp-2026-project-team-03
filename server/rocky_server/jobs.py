"""Job records and the single worker that runs songs one at a time.

The SGS workspace has one GPU, so jobs run strictly in order. Records are
JSON files on the shared volume; after an API restart, unfinished jobs are
queued again and unified.py --resume continues from the last finished stage.
"""

from __future__ import annotations

import json
import os
import logging
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .runners import NoAgent, PodTimeout, RunnerError, TransientPodFailure, to_wav

STATES = ("uploading", "queued", "running", "publishing", "cancelling", "cancelled", "complete", "failed")


@dataclass
class Job:
    id: str
    title: str
    filename: str
    requested: list[str]
    state: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    # what the app asked for besides `requested` (kept for the pipeline; unified.py does not read them yet)
    original: list[str] = field(default_factory=list)
    lineup: list[str] = field(default_factory=list)
    # a short message for the app while the song waits, e.g. for the GPU
    note: str | None = None
    # unified.py --original / --requested (keyboard,bass,guitar1|guitar2,drums; original may be "unknown")
    pipeline_original: str = "unknown"
    pipeline_requested: str = ""
    # set when unified.py refused the input (state is then "failed"):
    # too_short, silent or not_band_audio. The app shows its own message for it.
    reason: str | None = None
    # set for every other failure (see describe_failure): what the app tells the user and offers.
    # `error` above stays the developer's text (exception or pipeline error).
    error_code: str | None = None       # pdf_network, timeout, no_agent, pipeline_error, upload_interrupted
    user_message: str | None = None     # Korean, for people: what happened and what to do
    retryable: bool = False             # POST /jobs/{id}/retry is worth calling
    retry_after_sec: int | None = None  # wait this long before retrying (None: right away)
    retry_from: str | None = None       # "pdf": only the PDF stage runs again; "gpu": from the stage that stopped
    # "band": a score for every part of the user's band. "personal": solo practice, one instrument
    # (guitar may be two). Personal scores are never shared to a band.
    mode: str = "band"


class JobStore:
    def __init__(self, root: Path, runs: Path, inputs: Path) -> None:
        self.root, self.runs, self.inputs = root, runs, inputs
        for d in (root, runs, inputs):
            d.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.on_save: Callable[[Job], None] | None = None
        self.on_purge: Callable[[str], None] | None = None
        self._recorded_state: dict[str, tuple] = {}
        self.pending_purges: set[str] = set()  # deletes to finish after a storage or database error

    def path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def run_dir(self, job_id: str) -> Path:
        return self.runs / job_id

    def log(self, job_id: str) -> Path:
        return self.root / f"{job_id}.log"

    def save(self, job: Job) -> None:
        tmp = self.path(job.id).with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path(job.id))
        # Progress-note updates are frequent; the analysis ledger only needs
        # lifecycle changes. Avoid manifest reads and SQLite writes on each note.
        state = (job.state, job.started_at, job.finished_at, job.error_code, job.reason)
        if self.on_save is not None and self._recorded_state.get(job.id) != state:
            try:
                self.on_save(job)
                self._recorded_state[job.id] = state
            except Exception:
                logging.exception("Could not record experiment state for job %s", job.id)

    def get(self, job_id: str) -> Job | None:
        try:
            return Job(**json.loads(self.path(job_id).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def all(self) -> list[Job]:
        jobs = [self.get(p.stem) for p in self.root.glob("*.json")]
        return sorted((j for j in jobs if j), key=lambda j: j.created_at)

    def create(self, title: str, filename: str, requested: list[str],
               original: list[str] | None = None, lineup: list[str] | None = None,
               pipeline_original: str = "unknown", pipeline_requested: str = "", mode: str = "band") -> Job:
        # "uploading" until the file is fully saved, so no worker picks it up early.
        job = Job(id=uuid.uuid4().hex[:12], title=title, filename=filename, requested=requested,
                  state="uploading", original=original or [], lineup=lineup or [],
                  pipeline_original=pipeline_original,
                  pipeline_requested=pipeline_requested or ",".join(requested), mode=mode)
        self.save(job)
        return job

    # ---- delete (NFR-07): remove the song and its experiment row ----

    def tombstone(self, job_id: str) -> Path:
        """Marks a job the user deleted while it was still running; it is purged when it stops."""
        return self.root / f"{job_id}.deleted"

    def is_deleted(self, job_id: str) -> bool:
        return job_id in self.pending_purges or self.tombstone(job_id).exists()

    def purge(self, job_id: str) -> bool:
        """Remove the record, log, upload, run folder (results and key changes) and the mark.

        False means something is left: the song stays hidden and Worker tries again."""
        # Song files go first, and a failure here must not skip the database rows.
        shutil.rmtree(self.run_dir(job_id), ignore_errors=True)
        complete = not self.run_dir(job_id).exists()
        try:
            for f in [*self.inputs.glob(f"{job_id}.*"), self.log(job_id)]:
                f.unlink(missing_ok=True)
        except OSError:
            logging.exception("Could not delete files for job %s", job_id)
            complete = False
        if self.on_purge is not None:
            try:
                self.on_purge(job_id)
            except Exception:
                logging.exception("Could not delete experiment rows for job %s", job_id)
                complete = False
        if complete:
            try:
                for f in (self.path(job_id), self.tombstone(job_id)):
                    f.unlink(missing_ok=True)
            except OSError:
                logging.exception("Could not delete the record of job %s", job_id)
                complete = False
        if not complete:
            self.pending_purges.add(job_id)
            try:  # survives a restart when the disk allows it; the set above covers this process
                self.tombstone(job_id).touch()
            except OSError:
                logging.exception("Could not mark job %s as deleted", job_id)
            return False
        self.pending_purges.discard(job_id)
        self._recorded_state.pop(job_id, None)
        return True

    def update(self, job: Job, **changes) -> Job:
        with self.lock:
            current = self.get(job.id)
            if current is None:
                # The record was purged (the user deleted the song). A stale Job object must not
                # write it back: the delete contract (NFR-07) is that nothing of it stays.
                return job
            # A worker may hold an older Job object while the cancel endpoint
            # changes its state. Progress updates must not revive that job.
            if current.state in ("cancelling", "cancelled") and changes.get("state") != "cancelled":
                job.__dict__.update(current.__dict__)
                return current
            for key, value in changes.items():
                setattr(current, key, value)
            self.save(current)
            job.__dict__.update(current.__dict__)
        return current


class Worker:
    """Runs queued jobs in creation order, up to `parallel` at a time.

    Each running job holds one GPU while its GPU Job runs, so `parallel`
    should equal the number of GPUs the workspace can use at once
    (ROCKY_PARALLEL, default 1).
    """

    # The PDF stage only renders files that are already on the volume, so a Pod that failed for a
    # passing reason (TransientPodFailure: e.g. the mirror reset the connection while installing
    # MuseScore) is tried again before the song is marked failed; the GPU stage is not repeated.
    # Timeouts, a missing agent and real errors are not retried, and no retry starts after
    # PDF_STAGE_DEADLINE_SEC, so one song cannot hold the worker much longer than before.
    PDF_ATTEMPTS = 3
    PDF_RETRY_WAIT_SEC = 20.0
    PDF_STAGE_DEADLINE_SEC = 15 * 60.0

    def __init__(self, store: JobStore, runner, parallel: int = 1, abandon_sec: float | None = None) -> None:
        self.store, self.runner = store, runner
        self.parallel = max(1, parallel)
        # The app polls GET /jobs/{id} every 2 s while it waits for a song. When the phone loses the
        # internet the app cancels the song on its side (2nd UAT); a song nobody has asked about for
        # `abandon_sec` is cancelled here too, so it leaves the queue and stops holding a GPU.
        # Only songs the app has asked about since this server started are watched. 0 turns it off.
        self.abandon_sec = float(os.environ.get("ROCKY_ABANDON_SEC", "180")) if abandon_sec is None else abandon_sec
        self.last_seen: dict[str, float] = {}
        self.seen_lock = threading.Lock()
        self.cond = threading.Condition()
        self.stranded: set[str] = set()  # jobs whose run() ended before saving a final state
        self.stranded_lock = threading.Lock()
        self.threads = [threading.Thread(target=self._loop, name=f"rocky-worker-{i}", daemon=True)
                        for i in range(self.parallel)]

    def start(self) -> None:
        # Jobs cut off by a restart are run again; --resume skips finished stages.
        for job in self.store.all():
            if self.store.is_deleted(job.id):  # deleted before the restart: never run it again
                self.store.purge(job.id)
                continue
            if job.state in ("running", "publishing"):
                # A restarted attempt starts its own timer when claimed; do not
                # count API downtime or the new queue wait as processing time.
                self.store.update(job, state="queued", started_at=None, finished_at=None)
            elif job.state == "cancelling":
                # The request was already persisted. Never restart its pipeline.
                self.store.update(job, state="cancelled", finished_at=time.time())
            elif job.state == "uploading":  # the upload was cut off by the restart
                self.store.update(job, state="failed", error="upload interrupted",
                                  **UPLOAD_INTERRUPTED)
        for t in self.threads:
            t.start()
        self.notify()

    def notify(self) -> None:
        with self.cond:
            self.cond.notify_all()

    def seen(self, job_id: str, now: float | None = None) -> None:
        """The app asked about this song (upload or status poll)."""
        with self.seen_lock:
            self.last_seen[job_id] = time.time() if now is None else now

    def drop_abandoned(self, now: float | None = None) -> list[str]:
        """Cancel queued or running songs the app stopped asking about. Returns their ids."""
        if self.abandon_sec <= 0:
            return []
        now = time.time() if now is None else now
        with self.seen_lock:
            stale = [j for j, t in self.last_seen.items() if now - t > self.abandon_sec]
        dropped = []
        for job_id in stale:
            job = self.store.get(job_id)
            if job is not None and job.state in ("queued", "running", "publishing"):
                try:
                    self.cancel(job_id)
                    dropped.append(job_id)
                    logging.info("Cancelled job %s: the app stopped asking about it", job_id)
                except Exception:  # a runner that cannot stop it: try again next round
                    logging.exception("Could not cancel abandoned job %s", job_id)
                    continue
            with self.seen_lock:
                self.last_seen.pop(job_id, None)
        return dropped

    def queue_position(self, job_id: str) -> int | None:
        queued = [j.id for j in self.store.all()
                  if j.state == "queued" and not self.store.is_deleted(j.id)]
        return queued.index(job_id) + 1 if job_id in queued else None

    def claim(self) -> Job | None:
        """Take the oldest queued job and mark it running, so no other thread takes it."""
        with self.store.lock:
            job = next((j for j in self.store.all()
                        if j.state == "queued" and not self.store.is_deleted(j.id)), None)
            if job is not None:
                job.state = "running"
                job.started_at = job.started_at or time.time()
                job.error = None
                job.reason = None
                job.__dict__.update(CLEAR_FAILURE)
                self.store.save(job)
            return job

    def _loop(self) -> None:
        while True:
            try:
                self._settle_unfinished()
                self.drop_abandoned()
                job = self.claim()
            except Exception:  # e.g. a full volume: keep the worker and try again later
                logging.exception("Worker could not read or claim the queue")
                job = None
            if job is None:
                with self.cond:
                    self.cond.wait(timeout=30)
                continue
            try:
                self.run(job)
            except Exception:  # one song's cleanup error must not stop the queue
                logging.exception("Worker could not finish job %s", job.id)
                with self.stranded_lock:
                    self.stranded.add(job.id)

    def _settle_unfinished(self) -> None:
        """Retry the final state of interrupted jobs and any unfinished deletes."""
        with self.stranded_lock:
            job_ids, self.stranded = self.stranded, set()
        for job_id in job_ids:
            try:
                self._settle(job_id)
            except Exception:
                logging.exception("Could not save the final state of job %s", job_id)
                with self.stranded_lock:
                    self.stranded.add(job_id)
        for job_id in list(self.store.pending_purges):
            self.store.purge(job_id)

    def _settle(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        if job.state == "cancelling":
            self._finish_cancel(job)
        elif job.state in ("running", "publishing"):
            error = RunnerError("the server could not save this job's state")
            self.store.update(job, state="failed", finished_at=time.time(), note=None, error=str(error),
                              **describe_failure(self.store.run_dir(job_id), error))
        if self.store.is_deleted(job_id):
            self.store.purge(job_id)

    def cancel(self, job_id: str) -> str:
        """Persist cancellation before signalling the runner or waking the queue."""
        with self.store.lock:
            job = self.store.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.state in ("complete", "failed", "cancelled", "cancelling"):
                return job.state
            if job.state in ("running", "publishing") and not callable(getattr(self.runner, "cancel", None)):
                raise NotImplementedError("this runner cannot stop an active job")
            active = job.state in ("running", "publishing")
            job.state = "cancelling" if active else "cancelled"
            job.note = None
            job.error = None
            if not active:
                job.finished_at = time.time()
            self.store.save(job)
        if active:
            self.runner.cancel(job_id)
        else:
            self._clear_cancelled_files(job)
        self.notify()
        return job.state

    def retry(self, job_id: str) -> dict:
        """Put a failed song back in the queue under the same id (POST /jobs/{id}/retry).

        Checked and changed in one step under the store lock, like delete() above, so a song
        the user deleted is never brought back. Raises RetryRefused with the HTTP status."""
        with self.store.lock:
            job = self.store.get(job_id)
            if job is None or self.store.is_deleted(job_id):
                raise RetryRefused(404, "no such job")
            if job.state != "failed":
                raise RetryRefused(409, f"only a failed song can be retried (state is {job.state})")
            if job.reason:  # the input itself was refused; the same file gives the same answer
                raise RetryRefused(409, "this file was refused; upload a different one")
            if not job.retryable:
                raise RetryRefused(409, job.user_message or "this failure cannot be retried; upload the song again")
            if not (self.store.inputs / job.filename).is_file():
                raise RetryRefused(410, "the uploaded audio is gone; upload the song again")
            retry_from = job.retry_from
            job.state, job.error, job.note, job.started_at, job.finished_at = "queued", None, None, None, None
            job.__dict__.update(CLEAR_FAILURE)
            self.store.save(job)
        forget = getattr(self.runner, "forget", None)
        if callable(forget):
            forget(job_id)
        self.notify()
        return {"id": job_id, "state": "queued", "retry_from": retry_from,
                "queue_position": self.queue_position(job_id)}

    def delete(self, job_id: str) -> str | None:
        """Delete a job and all its files. None if there is no such job.

        "deleted": gone now. "pending": the song is still uploading or its Pod is
        being stopped (cancel above); it is purged as soon as that finishes.
        """
        # Read the state and leave the mark under the store lock, so a concurrent retry either
        # happened before (and is cancelled below as a queued song) or sees the mark and refuses.
        with self.store.lock:
            job = self.store.get(job_id)
            if job is None:
                return None
            self.store.tombstone(job_id).touch()
        if job.state == "uploading":  # create_job purges it when the upload ends
            return "pending"
        if job.state in ("queued", "running", "publishing", "cancelling"):
            try:
                if self.cancel(job_id) == "cancelling":
                    return "pending"
            except NotImplementedError:
                return "pending"  # this runner cannot stop it: purged when it ends
        return "deleted" if self.store.purge(job_id) else "pending"

    def _clear_cancelled_files(self, job: Job) -> None:
        shutil.rmtree(self.store.run_dir(job.id), ignore_errors=True)
        if job.filename:
            free_space(self.store.run_dir(job.id), self.store.inputs, job.filename)

    def _finish_cancel(self, job: Job) -> None:
        current = self.store.get(job.id)
        if current is None or current.state not in ("cancelling", "cancelled"):
            return
        self.store.update(current, state="cancelled", finished_at=time.time(), note=None)
        self._clear_cancelled_files(current)
        forget = getattr(self.runner, "forget", None)
        if callable(forget):
            forget(job.id)
        if self.store.is_deleted(job.id):
            self.store.purge(job.id)

    def _is_cancelling(self, job_id: str) -> bool:
        current = self.store.get(job_id)
        return current is not None and current.state in ("cancelling", "cancelled")

    def _publish(self, job: Job, run: Path, log: Path, note) -> None:
        attempts = max(1, int(self.PDF_ATTEMPTS))
        stop_retrying_at = time.monotonic() + self.PDF_STAGE_DEADLINE_SEC
        for attempt in range(1, attempts + 1):
            try:
                self.runner.run_pdf(job.id, run, log, note=note)
                return
            except TransientPodFailure:
                if (attempt == attempts or self._is_cancelling(job.id)
                        or time.monotonic() + self.PDF_RETRY_WAIT_SEC > stop_retrying_at):
                    raise
            with log.open("a", encoding="utf-8") as out:
                out.write(f"PDF stage failed for a passing reason (attempt {attempt}/{attempts}); trying again\n")
            note(f"악보 PDF 만들기를 다시 시도하는 중 ({attempt + 1}/{attempts})")
            time.sleep(self.PDF_RETRY_WAIT_SEC)
            if self._is_cancelling(job.id):
                raise RunnerError(f"job {job.id} was cancelled while waiting to retry the PDF stage")

    def run(self, job: Job) -> None:
        store = self.store
        log = store.log(job.id)
        run = store.run_dir(job.id)
        job = store.update(job, state="running", started_at=job.started_at or time.time(), error=None)
        if self._is_cancelling(job.id):
            self._finish_cancel(job)
            return
        try:
            audio = to_wav(store.inputs / job.filename)
            if self._is_cancelling(job.id):
                self._finish_cancel(job)
                return
            def note(msg: str | None) -> None:
                if msg != job.note:
                    store.update(job, note=msg)

            if not (run / "full_score.mid").is_file():
                self.runner.run_midi(job.id, audio, run, job.pipeline_requested, log, note=note,
                                     original=job.pipeline_original,
                                     # --personal needs an unknown original; a guitar-count redo
                                     # sends the original, and then only those stems are transcribed
                                     personal=job.mode == "personal" and job.pipeline_original == "unknown")
            if self._is_cancelling(job.id):
                self._finish_cancel(job)
                return
            store.update(job, state="publishing", note=None)
            if self._is_cancelling(job.id):
                self._finish_cancel(job)
                return
            if not (run / "scores" / "score_outputs.json").is_file():
                self._publish(job, run, log, note)
            if self._is_cancelling(job.id):
                self._finish_cancel(job)
                return
            if not (run / "scores" / "score_outputs.json").is_file():
                raise RunnerError("PDF stage finished without scores/score_outputs.json")
            store.update(job, state="complete", finished_at=time.time(), note=None)
            if self._is_cancelling(job.id):
                self._finish_cancel(job)
                return
            free_space(run, store.inputs, job.filename)
        except Exception as exc:  # any failure ends this job, never the worker
            if self._is_cancelling(job.id):
                self._finish_cancel(job)
                return
            rejection = input_rejection(run)
            if rejection is not None:
                # Not a server fault: the song was refused right after separation.
                # Retrying gives the same answer, so the large stems can go now.
                code = str(rejection.get("code") or "not_band_audio")
                store.update(job, state="failed", finished_at=time.time(), note=None, reason=code,
                             error=REJECTION_MESSAGES.get(code, REJECTION_MESSAGES["not_band_audio"]))
                free_space(run, store.inputs, job.filename)
            else:
                store.update(job, state="failed", finished_at=time.time(), note=None, error=failure_reason(run, exc),
                             **describe_failure(run, exc, getattr(self.runner, "timeout_sec", None)))
        finally:
            if store.is_deleted(job.id) and not self._is_cancelling(job.id):
                store.purge(job.id)


REJECTION_MESSAGES = {
    "too_short": "곡이 너무 짧아서 악보를 만들 수 없어요.",
    "silent": "소리가 거의 들리지 않는 파일이에요.",
    "not_band_audio": "밴드 악기(드럼·베이스·기타·키보드) 소리가 거의 들리지 않아요. 밴드 곡을 올려 주세요.",
}


def input_rejection(run: Path) -> dict | None:
    """unified.py's input_check verdict, if it refused the song (manifest status "rejected")."""
    try:
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("status") != "rejected":
        return None
    return manifest.get("rejection") or {}


def failure_reason(run: Path, exc: Exception) -> str:
    """Prefer the pipeline's own error from manifest.json; it names the stage."""
    try:
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") == "failed" and manifest.get("error"):
            return str(manifest["error"])[:500]
    except (OSError, ValueError):
        pass
    return f"{type(exc).__name__}: {exc}"[:500]


class RetryRefused(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


CLEAR_FAILURE = dict(error_code=None, user_message=None, retryable=False, retry_after_sec=None,
                     retry_from=None)

UPLOAD_INTERRUPTED = dict(
    error_code="upload_interrupted", retryable=False, retry_after_sec=None, retry_from=None,
    user_message="음원을 올리는 중에 연결이 끊겼어요. 처음부터 다시 올려 주세요.")

PDF_NETWORK_RETRY_AFTER_SEC = 60


def describe_failure(run: Path, exc: Exception, timeout_sec: float | None = None) -> dict:
    """What the app shows for a failed song, and whether POST /jobs/{id}/retry can help.

    retry_from follows the worker: a run that already has full_score.mid only runs the PDF stage
    again; otherwise unified.py --resume continues from the stage that stopped."""
    from_pdf = (run / "full_score.mid").is_file()
    retry_from = "pdf" if from_pdf else "gpu"
    redo = ("'다시 시도'를 누르면 채보 결과는 그대로 두고 악보 파일(PDF)만 다시 만들어요. 약 1~2분 걸려요."
            if from_pdf else
            "'다시 시도'를 누르면 이미 끝난 단계는 건너뛰고 멈춘 단계부터 이어서 해요. 길어도 10분 안팎이에요.")
    if isinstance(exc, TransientPodFailure):
        return dict(error_code="pdf_network", retryable=True, retry_after_sec=PDF_NETWORK_RETRY_AFTER_SEC,
                    retry_from=retry_from,
                    user_message="악보 파일(PDF)을 만드는 프로그램을 준비하다가 인터넷 연결이 끊겼어요. "
                                 f"{PDF_NETWORK_RETRY_AFTER_SEC}초쯤 기다린 뒤 " + redo)
    if isinstance(exc, NoAgent):
        return dict(error_code="no_agent", retryable=False, retry_after_sec=None, retry_from=retry_from,
                    user_message="지금 악보를 만드는 컴퓨터가 서버에 연결되어 있지 않아서 시작하지 못했어요. "
                                 "다시 시도해도 같은 결과가 나와요. 팀에게 알려 주세요.")
    if isinstance(exc, PodTimeout):
        minutes = round((timeout_sec or 5400) / 60)
        return dict(error_code="timeout", retryable=True, retry_after_sec=None, retry_from=retry_from,
                    user_message=f"{minutes}분 안에 끝나지 않아서 멈췄어요. 지금 바로 " + redo)
    return dict(error_code="pipeline_error", retryable=True, retry_after_sec=None, retry_from=retry_from,
                user_message="악보를 만드는 중에 오류가 났어요. 지금 바로 " + redo +
                             " 같은 곡이 두 번 실패하면 팀에게 알려 주세요.")


def free_space(run: Path, inputs: Path, filename: str) -> None:
    """The shared volume has only a few GiB free. After a job is complete,
    remove what the app never downloads: the separated audio stems (about
    150 MB per song) and the uploaded/decoded audio. MIDI, TAB and PDF stay."""
    shutil.rmtree(run / "stems", ignore_errors=True)
    stem = Path(filename).stem
    for f in inputs.glob(f"{stem}.*"):
        f.unlink(missing_ok=True)
