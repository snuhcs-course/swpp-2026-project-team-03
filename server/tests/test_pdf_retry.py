"""The PDF stage is tried again (without repeating the GPU stage) only after a passing failure."""

import time

import pytest
from fastapi.testclient import TestClient

from rocky_server.app import create_app
from rocky_server.jobs import JobStore
from rocky_server.runners import TRANSIENT_MARKER, RunnerError, TransientPodFailure, pod_failure

from fake_pipeline import FakeRunner


class FlakyPdfRunner(FakeRunner):
    """The first `failures` PDF attempts raise `error` (by default: the mirror reset the download)."""

    def __init__(self, failures, error=None):
        super().__init__()
        self.failures = failures
        self.error = error

    def run_pdf(self, job_id, run, log, note=lambda _m: None):
        if self.failures > 0:
            self.failures -= 1
            self.calls.append(("pdf", job_id))
            raise self.error or TransientPodFailure(f"pdf pod Failed; see {job_id}.log")
        super().run_pdf(job_id, run, log, note)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("ROCKY_API_KEY", raising=False)

    def make(runner):
        store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
        app = create_app(store, runner, start_worker=False)
        worker = app.state.worker
        worker.PDF_RETRY_WAIT_SEC = 0
        return TestClient(app), store, worker
    return make


def upload(client):
    r = client.post("/jobs", files={"file": ("song.wav", b"RIFF....WAVE", "audio/wav")},
                    data={"requested": "piano,guitar", "title": "Song"})
    assert r.status_code == 201
    return r.json()["id"]


def pdf_calls(runner, job_id):
    return [c for c in runner.calls if c == ("pdf", job_id)]


def test_a_passing_pdf_failure_is_retried_without_repeating_the_gpu_stage(setup):
    runner = FlakyPdfRunner(failures=2)
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))
    assert [c[0] for c in runner.calls] == ["midi", "pdf", "pdf", "pdf"]
    assert client.get(f"/jobs/{job_id}").json()["state"] == "complete"
    assert "(attempt 1/3); trying again" in store.log(job_id).read_text()


def test_song_fails_after_the_last_pdf_attempt(setup):
    runner = FlakyPdfRunner(failures=5)
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))
    assert len(pdf_calls(runner, job_id)) == 3
    s = client.get(f"/jobs/{job_id}").json()
    assert s["state"] == "failed" and "pdf pod Failed" in s["error"]


@pytest.mark.parametrize("error", [
    RunnerError("pdf pod did not finish within 5400 s"),        # timeout, e.g. no agent picked it up
    RunnerError("pdf pod Failed; see x.log"),                     # a real error in publish_scores
    RunnerError("job x was cancelled before pdf Pod creation"),
])
def test_timeouts_missing_agent_and_real_errors_are_not_retried(setup, error):
    runner = FlakyPdfRunner(failures=5, error=error)
    client, store, worker = setup(runner)
    worker.PDF_RETRY_WAIT_SEC = 3600  # a retry would hang the test
    first, second = upload(client), upload(client)

    started = time.monotonic()
    worker.run(store.get(first))
    assert time.monotonic() - started < 5
    assert len(pdf_calls(runner, first)) == 1
    assert client.get(f"/jobs/{first}").json()["state"] == "failed"

    # the worker is free again: the next queued song runs to the end
    runner.failures = 0
    worker.run(store.get(second))
    assert client.get(f"/jobs/{second}").json()["state"] == "complete"


def test_no_retry_starts_after_the_pdf_stage_deadline(setup):
    runner = FlakyPdfRunner(failures=5)
    client, store, worker = setup(runner)
    worker.PDF_STAGE_DEADLINE_SEC = 0
    job_id = upload(client)
    worker.run(store.get(job_id))
    assert len(pdf_calls(runner, job_id)) == 1
    assert client.get(f"/jobs/{job_id}").json()["state"] == "failed"


def test_a_cancelled_song_is_not_retried(setup):
    runner = FlakyPdfRunner(failures=5)
    client, store, worker = setup(runner)
    job_id = upload(client)
    original = runner.run_pdf

    def cancel_then_fail(job, run, log, note=lambda _m: None):
        client.post(f"/jobs/{job}/cancel")
        original(job, run, log, note)
    runner.run_pdf = cancel_then_fail
    worker.run(store.get(job_id))
    assert len(pdf_calls(runner, job_id)) == 1
    assert client.get(f"/jobs/{job_id}").json()["state"] == "cancelled"


def test_only_a_pod_that_printed_the_marker_is_transient():
    marked = pod_failure("pdf pod", "Failed", f"...\n{TRANSIENT_MARKER}: could not install\n", "x.log")
    plain = pod_failure("pdf pod", "Failed", "Traceback ...\nValueError: bad score\n", "x.log")
    no_log = pod_failure("pdf pod", None, "", "x.log")
    assert type(marked) is TransientPodFailure and str(marked) == "pdf pod Failed; see x.log"
    assert type(plain) is RunnerError and type(no_log) is RunnerError
