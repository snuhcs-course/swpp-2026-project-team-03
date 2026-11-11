"""The PDF stage is tried again (without repeating the GPU stage) before a song fails."""

import pytest
from fastapi.testclient import TestClient

from rocky_server.app import create_app
from rocky_server.jobs import JobStore
from rocky_server.runners import RunnerError

from fake_pipeline import FakeRunner


class FlakyPdfRunner(FakeRunner):
    """The first `failures` PDF attempts fail like a Pod whose apt download was cut off."""

    def __init__(self, failures):
        super().__init__()
        self.failures = failures

    def run_pdf(self, job_id, run, log, note=lambda _m: None):
        if self.failures > 0:
            self.failures -= 1
            self.calls.append(("pdf", job_id))
            raise RunnerError(f"pdf pod Failed; see {job_id}.log")
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


def test_pdf_stage_is_retried_without_repeating_the_gpu_stage(setup):
    runner = FlakyPdfRunner(failures=2)
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))
    assert [c[0] for c in runner.calls] == ["midi", "pdf", "pdf", "pdf"]
    assert client.get(f"/jobs/{job_id}").json()["state"] == "complete"
    assert "PDF stage failed (attempt 1/3); trying again" in store.log(job_id).read_text()


def test_song_fails_after_the_last_pdf_attempt(setup):
    runner = FlakyPdfRunner(failures=5)
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))
    assert [c[0] for c in runner.calls] == ["midi", "pdf", "pdf", "pdf"]
    s = client.get(f"/jobs/{job_id}").json()
    assert s["state"] == "failed" and "pdf pod Failed" in s["error"]


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
    assert [c[0] for c in runner.calls].count("pdf") == 1
    assert client.get(f"/jobs/{job_id}").json()["state"] == "cancelled"
