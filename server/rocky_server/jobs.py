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

from .runners import RunnerError, to_wav

STATES = ("uploading", "queued", "running", "publishing", "complete", "failed")


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

    def update(self, job: Job, **changes) -> Job:
        with self.lock:
            for key, value in changes.items():
                setattr(job, key, value)
            self.save(job)
        return job


class Worker:
    """Runs queued jobs in creation order, up to `parallel` at a time.

    Each running job holds one GPU while its GPU Job runs, so `parallel`
    should equal the number of GPUs the workspace can use at once
    (ROCKY_PARALLEL, default 1).
    """

    def __init__(self, store: JobStore, runner, parallel: int = 1) -> None:
        self.store, self.runner = store, runner
        self.parallel = max(1, parallel)
        self.cond = threading.Condition()
        self.threads = [threading.Thread(target=self._loop, name=f"rocky-worker-{i}", daemon=True)
                        for i in range(self.parallel)]

    def start(self) -> None:
        # Jobs cut off by a restart are run again; --resume skips finished stages.
        for job in self.store.all():
            if job.state in ("running", "publishing"):
                self.store.update(job, state="queued")
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

    def run(self, job: Job) -> None:
        store = self.store
        log = store.log(job.id)
        run = store.run_dir(job.id)
        store.update(job, state="running", started_at=job.started_at or time.time(), error=None)
        try:
            audio = to_wav(store.inputs / job.filename)
            def note(msg: str | None) -> None:
                if msg != job.note:
                    store.update(job, note=msg)

            if not (run / "full_score.mid").is_file():
                self.runner.run_midi(job.id, audio, run, job.pipeline_requested, log, note=note,
                                     original=job.pipeline_original)
            store.update(job, state="publishing", note=None)
            if not (run / "scores" / "score_outputs.json").is_file():
                self.runner.run_pdf(job.id, run, log, note=note)
            if not (run / "scores" / "score_outputs.json").is_file():
                raise RunnerError("PDF stage finished without scores/score_outputs.json")
            store.update(job, state="complete", finished_at=time.time(), note=None)
            free_space(run, store.inputs, job.filename)
        except Exception as exc:  # any failure ends this job, never the worker
            store.update(job, state="failed", finished_at=time.time(), note=None, error=failure_reason(run, exc))


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
