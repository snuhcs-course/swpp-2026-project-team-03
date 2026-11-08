"""The agent path end to end: API (ROCKY_RUNNER=agent) <-HTTP-> rocky_agent.py <-> fake kubectl.

The fake kubectl runs ci_fake_pipeline.py as the "Pod", so the API sees the
same files a real run writes. No cluster or GPU is needed.
"""

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from rocky_server.agent_runner import WAIT_FOR_AGENT, AgentRunner
from rocky_server.app import create_app
from rocky_server.jobs import JobStore

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent / "agent" / "rocky_agent.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.delenv("ROCKY_API_KEY", raising=False)
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    runner = AgentRunner(timeout_sec=60)
    runner.POLL_SEC = 0.2
    app = create_app(store, runner)
    port = free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", store, runner, tmp_path
    srv.should_exit = True
    t.join(5)


def start_agent(url, tmp_path, quota_refusals=0, name="laptop-1"):
    env = {"FAKE_KUBE_DIR": str(tmp_path / "kube"), "FAKE_KUBE_QUOTA_REFUSALS": str(quota_refusals),
           "PATH": "/usr/bin:/bin"}
    return subprocess.Popen(
        [sys.executable, str(AGENT), "--api", url, "--kubectl", str(HERE / "fake_kubectl.py"),
         "--name", name, "--poll", "0.2", "--beat", "0.2", "--quota-retry", "0.3"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def upload(url):
    import httpx
    r = httpx.post(f"{url}/jobs", files={"file": ("song.wav", b"RIFF....WAVE", "audio/wav")},
                   data={"requested": "piano,guitar", "lineup": "piano,drums,guitar", "title": "agent test"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def wait_state(store, job_id, states, seconds=40):
    for _ in range(int(seconds / 0.1)):
        job = store.get(job_id)
        if job.state in states:
            return job
        time.sleep(0.1)
    return store.get(job_id)


def test_song_completes_through_laptop_agent(server):
    url, store, runner, tmp = server
    agent = start_agent(url, tmp, quota_refusals=2)
    try:
        job_id = upload(url)
        job = wait_state(store, job_id, {"complete", "failed"})
        assert job.state == "complete", (job.error, store.log(job_id).read_text())
        import httpx
        result = httpx.get(f"{url}/jobs/{job_id}/result").json()
        assert result["full_band"]["mp3"] == "scores/band.mp3"
        # both Pods were deleted after they finished (GPU released). The agent
        # reports "done" first and deletes the Pod right after, so allow a moment.
        for _ in range(50):
            if not list((tmp / "kube").glob("*.json")):
                break
            time.sleep(0.1)
        assert not list((tmp / "kube").glob("*.json"))
        log = store.log(job_id).read_text()
        assert "rocky-midi-" in log and "rocky-pdf-" in log
    finally:
        agent.terminate()
        out = agent.communicate(timeout=5)[0]
    assert "GPU 할당량이 차 있어서 기다림" in out    # quota refusals were waited out


def test_without_agent_the_app_is_told_to_wait(server):
    url, store, runner, tmp = server
    job_id = upload(url)
    for _ in range(50):
        if store.get(job_id).note == WAIT_FOR_AGENT:
            break
        time.sleep(0.1)
    import httpx
    assert httpx.get(f"{url}/jobs/{job_id}").json()["note"] == WAIT_FOR_AGENT
    # an agent started later still picks the song up
    agent = start_agent(url, tmp)
    try:
        assert wait_state(store, job_id, {"complete", "failed"}).state == "complete"
    finally:
        agent.terminate()
        agent.communicate(timeout=5)


def test_failed_pod_fails_the_song(server, monkeypatch):
    url, store, runner, tmp = server
    # make the fake pipeline fail: an audio path that is a directory makes nothing special,
    # so instead report a failure directly as an agent would
    job_id = upload(url)
    for _ in range(50):
        req = runner.next_request("tester")
        if req:
            break
        time.sleep(0.1)
    assert req and req["kind"] == "midi"
    assert req["pod"]["spec"]["nodeSelector"] == {"kubernetes.io/hostname": "ferrari"}
    assert runner.finish(req["rid"], "tester", "Failed", "Traceback: boom")
    job = wait_state(store, job_id, {"complete", "failed"})
    assert job.state == "failed"
    assert "boom" in store.log(job_id).read_text()


def test_requests_go_to_one_agent_and_move_when_it_stops(server):
    url, store, runner, tmp = server
    upload(url)
    for _ in range(50):
        first = runner.next_request("a")
        if first:
            break
        time.sleep(0.1)
    assert first is not None
    assert runner.next_request("b") is None            # taken by a
    assert runner.heartbeat(first["rid"], "a", None)
    assert not runner.heartbeat(first["rid"], "b", None)
    runner.requests[first["rid"]].last_seen -= runner.STALE_SEC + 1   # a went silent
    again = runner.next_request("b")
    assert again["rid"] == first["rid"] and again["pod"] == first["pod"]
    assert runner.finish(first["rid"], "b", "Succeeded", "")


def test_cancel_request_waits_for_agent_pod_deletion(server):
    url, store, runner, _ = server
    job_id = upload(url)
    for _ in range(50):
        req = runner.next_request("laptop")
        if req:
            break
        time.sleep(0.1)
    assert req and req["job_id"] == job_id
    import httpx
    response = httpx.post(f"{url}/jobs/{job_id}/cancel")
    assert response.json()["state"] == "cancelling"
    signal = httpx.post(f"{url}/agent/requests/{req['rid']}/heartbeat",
                        json={"agent": "laptop", "note": None})
    assert signal.status_code == 410
    import importlib.util
    spec = importlib.util.spec_from_file_location("cancel_agent", AGENT)
    cancel_agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cancel_agent)
    with pytest.raises(cancel_agent.PodCancellationRequested):
        cancel_agent.Api(url, "", "laptop").heartbeat(req["rid"], None)
    assert runner.heartbeat(req["rid"], "laptop", None) == "cancel"
    assert store.get(job_id).state == "cancelling"
    assert runner.finish(req["rid"], "laptop", "Cancelled", "pod deleted")
    assert wait_state(store, job_id, {"cancelled", "failed"}).state == "cancelled"
