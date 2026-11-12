"""Job records and the single worker that runs songs one at a time.

The SGS workspace has one GPU, so jobs run strictly in order. Records are
JSON files on the shared volume; after an API restart, unfinished jobs are
queued again and unified.py --resume continues from the last finished stage.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .runners import RunnerError, TransientPodFailure, to_wav

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


class JobStore:
    def __init__(self, root: Path, runs: Path, inputs: Path) -> None:
        self.root, self.runs, self.inputs = root, runs, inputs
        for d in (root, runs, inputs):
            d.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

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
               pipeline_original: str = "unknown", pipeline_requested: str = "") -> Job:
        # "uploading" until the file is fully saved, so no worker picks it up early.
        job = Job(id=uuid.uuid4().hex[:12], title=title, filename=filename, requested=requested,
                  state="uploading", original=original or [], lineup=lineup or [],
                  pipeline_original=pipeline_original,
                  pipeline_requested=pipeline_requested or ",".join(requested))
        self.save(job)
        return job

    # ---- delete (NFR-07): the user removed the song, so the server keeps nothing of it ----

    def tombstone(self, job_id: str) -> Path:
        """Marks a job the user deleted while it was still running; it is purged when it stops."""
        return self.root / f"{job_id}.deleted"

    def is_deleted(self, job_id: str) -> bool:
        return self.tombstone(job_id).exists()

    def purge(self, job_id: str) -> None:
        """Remove the record, log, upload, run folder (results and key changes) and the mark."""
        shutil.rmtree(self.run_dir(job_id), ignore_errors=True)
        for f in self.inputs.glob(f"{job_id}.*"):
            f.unlink(missing_ok=True)
        for f in (self.log(job_id), self.path(job_id), self.tombstone(job_id)):
            f.unlink(missing_ok=True)

    def update(self, job: Job, **changes) -> Job:
        with self.lock:
            current = self.get(job.id) or job
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

    def __init__(self, store: JobStore, runner, parallel: int = 1) -> None:
        self.store, self.runner = store, runner
        self.parallel = max(1, parallel)
        self.cond = threading.Condition()
        self.threads = [threading.Thread(target=self._loop, name=f"rocky-worker-{i}", daemon=True)
                        for i in range(self.parallel)]

    def start(self) -> None:
        # Jobs cut off by a restart are run again; --resume skips finished stages.
        for job in self.store.all():
            if self.store.is_deleted(job.id):  # deleted before the restart: never run it again
                self.store.purge(job.id)
                continue
            if job.state in ("running", "publishing"):
                self.store.update(job, state="queued")
            elif job.state == "cancelling":
                # The request was already persisted. Never restart its pipeline.
                self.store.update(job, state="cancelled", finished_at=time.time())
            elif job.state == "uploading":  # the upload was cut off by the restart
                self.store.update(job, state="failed", error="upload interrupted")
        for t in self.threads:
            t.start()
        self.notify()

    def notify(self) -> None:
        with self.cond:
            self.cond.notify_all()

    def queue_position(self, job_id: str) -> int | None:
        queued = [j.id for j in self.store.all() if j.state == "queued"]
        return queued.index(job_id) + 1 if job_id in queued else None

    def claim(self) -> Job | None:
        """Take the oldest queued job and mark it running, so no other thread takes it."""
        with self.store.lock:
            job = next((j for j in self.store.all() if j.state == "queued"), None)
            if job is not None:
                job.state = "running"
                job.started_at = job.started_at or time.time()
                job.error = None
                job.reason = None
                self.store.save(job)
            return job

    def _loop(self) -> None:
        while True:
            job = self.claim()
            if job is None:
                with self.cond:
                    self.cond.wait(timeout=30)
                continue
            self.run(job)

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

    def delete(self, job_id: str) -> str | None:
        """Delete a job and all its files. None if there is no such job.

        "deleted": gone now. "pending": the song is still uploading or its Pod is
        being stopped (cancel above); it is purged as soon as that finishes.
        """
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
        self.store.purge(job_id)
        return "deleted"

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
                                     original=job.pipeline_original)
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
                store.update(job, state="failed", finished_at=time.time(), note=None, error=failure_reason(run, exc))
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


def free_space(run: Path, inputs: Path, filename: str) -> None:
    """The shared volume has only a few GiB free. After a job is complete,
    remove what the app never downloads: the separated audio stems (about
    150 MB per song) and the uploaded/decoded audio. MIDI, TAB and PDF stay."""
    shutil.rmtree(run / "stems", ignore_errors=True)
    stem = Path(filename).stem
    for f in inputs.glob(f"{stem}.*"):
        f.unlink(missing_ok=True)
