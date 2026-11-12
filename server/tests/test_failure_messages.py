"""Failed songs tell the user what happened and what to do; POST /jobs/{id}/retry reruns them."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from rocky_server.agent_runner import AgentRunner
from rocky_server.app import create_app
from rocky_server.jobs import JobStore
from rocky_server.runners import NoAgent, PodTimeout, TransientPodFailure

from fake_pipeline import FakeRunner


class ScriptedRunner(FakeRunner):
    """Raise the given errors at a stage, in order, then behave normally."""

    def __init__(self, midi_errors=(), pdf_errors=()):
        super().__init__()
        self.midi_errors, self.pdf_errors = list(midi_errors), list(pdf_errors)

    def run_midi(self, job_id, audio, run, requested, log, note=lambda _m: None, original="unknown"):
        if self.midi_errors:
            self.calls.append(("midi", job_id))
            raise self.midi_errors.pop(0)
        super().run_midi(job_id, audio, run, requested, log, note, original)

    def run_pdf(self, job_id, run, log, note=lambda _m: None):
        if self.pdf_errors:
            self.calls.append(("pdf", job_id))
            raise self.pdf_errors.pop(0)
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


def upload(client, data=b"RIFF....WAVE"):
    r = client.post("/jobs", files={"file": ("song.wav", data, "audio/wav")},
                    data={"requested": "piano,guitar", "title": "Song"})
    assert r.status_code == 201
    return r.json()["id"]


def stages(runner, job_id):
    return [c[0] for c in runner.calls if c[1] == job_id]


def test_pdf_network_failure_says_when_to_retry_and_retry_runs_only_the_pdf_stage(setup):
    runner = ScriptedRunner(pdf_errors=[TransientPodFailure("pdf pod Failed; see x.log")] * 3)
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))

    s = client.get(f"/jobs/{job_id}").json()
    assert s["state"] == "failed"
    assert (s["error_code"], s["retryable"], s["retry_after_sec"], s["retry_from"]) == ("pdf_network", True, 60, "pdf")
    assert "60초" in s["message"] and "PDF" in s["message"] and "채보 결과는 그대로" in s["message"]
    assert "pdf pod Failed" in s["error"]  # the developer's text is still there

    r = client.post(f"/jobs/{job_id}/retry")
    assert r.status_code == 200 and r.json()["retry_from"] == "pdf"
    s = client.get(f"/jobs/{job_id}").json()
    assert s["state"] == "queued" and s["message"] is None and s["error"] is None

    worker.run(worker.claim())
    assert stages(runner, job_id) == ["midi", "pdf", "pdf", "pdf", "pdf"]  # no second GPU stage
    assert client.get(f"/jobs/{job_id}").json()["state"] == "complete"


def test_timeout_before_the_gpu_stage_finished_resumes_from_the_gpu_stage(setup):
    runner = ScriptedRunner(midi_errors=[PodTimeout("midi pod did not finish within 5400 s")])
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))

    s = client.get(f"/jobs/{job_id}").json()
    assert (s["error_code"], s["retryable"], s["retry_after_sec"], s["retry_from"]) == ("timeout", True, None, "gpu")
    assert "90분" in s["message"] and "멈춘 단계부터" in s["message"]

    assert client.post(f"/jobs/{job_id}/retry").json()["retry_from"] == "gpu"
    worker.run(worker.claim())
    assert stages(runner, job_id) == ["midi", "midi", "pdf"]
    assert client.get(f"/jobs/{job_id}").json()["state"] == "complete"


def test_no_agent_is_not_offered_a_retry(setup):
    runner = ScriptedRunner(midi_errors=[NoAgent("no agent took the midi pod within 5400 s")])
    client, store, worker = setup(runner)
    job_id = upload(client)
    worker.run(store.get(job_id))

    s = client.get(f"/jobs/{job_id}").json()
    assert (s["error_code"], s["retryable"]) == ("no_agent", False)
    assert "팀에게 알려" in s["message"]
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409


def test_other_errors_are_retryable_and_ask_to_report_a_second_failure(setup):
    client, store, worker = setup(FakeRunner(fail_stage="midi"))
    job_id = upload(client)
    worker.run(store.get(job_id))
    s = client.get(f"/jobs/{job_id}").json()
    assert (s["error_code"], s["retryable"], s["retry_from"]) == ("pipeline_error", True, "gpu")
    assert "두 번 실패하면" in s["message"]
    assert "muscriptor_drums exited 1" in s["error"]


def test_retry_is_refused_for_songs_that_did_not_fail_or_were_refused(setup):
    client, store, worker = setup(FakeRunner())
    done = upload(client)
    worker.run(store.get(done))
    assert client.post(f"/jobs/{done}/retry").status_code == 409

    queued = upload(client)
    assert client.post(f"/jobs/{queued}/retry").status_code == 409


def test_a_refused_input_cannot_be_retried(setup):
    client, store, worker = setup(FakeRunner(fail_stage="reject"))
    job_id = upload(client)
    worker.run(store.get(job_id))
    assert client.get(f"/jobs/{job_id}").json()["reason"] == "not_band_audio"
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409


def test_retry_needs_the_uploaded_audio(setup):
    client, store, worker = setup(FakeRunner(fail_stage="midi"))
    job_id = upload(client)
    worker.run(store.get(job_id))
    (store.inputs / store.get(job_id).filename).unlink()
    assert client.post(f"/jobs/{job_id}/retry").status_code == 410


def test_agent_runner_tells_a_missing_agent_from_a_slow_pod(tmp_path):
    runner = AgentRunner(timeout_sec=0.4)
    runner.POLL_SEC = 0.05
    with pytest.raises(NoAgent):
        runner.run_pdf("abcabcabcabc", tmp_path, tmp_path / "log")

    def take_it():
        for _ in range(100):
            if runner.next_request("laptop"):
                return
            time.sleep(0.02)
    t = threading.Thread(target=take_it)
    t.start()
    with pytest.raises(PodTimeout) as err:
        runner.run_pdf("abcabcabcabc", tmp_path, tmp_path / "log")
    t.join()
    assert not isinstance(err.value, NoAgent)
