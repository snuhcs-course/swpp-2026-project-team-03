import pytest
from fastapi.testclient import TestClient

from rocky_server.app import create_app
from rocky_server.jobs import JobStore

from fake_pipeline import FakeRunner


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("ROCKY_API_KEY", raising=False)

    def make(runner=None, key=None):
        if key:
            monkeypatch.setenv("ROCKY_API_KEY", key)
        store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
        runner = runner or FakeRunner()
        app = create_app(store, runner, start_worker=False)
        return TestClient(app), store, runner, app.state.worker
    return make


def upload(client, name="song.wav", requested="piano,guitar", headers=None, data=b"RIFF....WAVE"):
    return client.post("/jobs", files={"file": (name, data, "audio/wav")},
                       data={"requested": requested, "title": "Immigrant Song"}, headers=headers or {})


def test_upload_queue_run_and_download(setup):
    client, store, runner, worker = setup()
    r = upload(client)
    assert r.status_code == 201
    job_id = r.json()["id"]
    s = client.get(f"/jobs/{job_id}").json()
    assert (s["state"], s["queue_position"], s["stage"], s["eta_sec"]) == ("queued", 1, "SEPARATE", None)
    assert client.get(f"/jobs/{job_id}/result").status_code == 409

    worker.run(store.get(job_id))
    assert runner.calls == [("midi", job_id, f"{job_id}.wav", "keyboard,guitar1", "unknown"), ("pdf", job_id)]
    s = client.get(f"/jobs/{job_id}").json()
    assert (s["state"], s["fraction"]) == ("complete", 1.0)

    result = client.get(f"/jobs/{job_id}/result").json()
    assert result["title"] == "Immigrant Song"
    assert result["full_band"]["pdf"] == "scores/full_band.pdf"
    f = client.get(f"/jobs/{job_id}/files/scores/full_band.pdf")
    assert f.status_code == 200 and f.content == b"%PDF-full"
    assert f.headers["content-type"] == "application/pdf"
    assert client.get(f"/jobs/{job_id}/files/scores/guitar.mid").status_code == 200
    mp3 = client.get(f"/jobs/{job_id}/files/scores/band.mp3")
    assert mp3.status_code == 200 and mp3.headers["content-type"] == "audio/mpeg"


def test_only_listed_files_can_be_downloaded(setup):
    client, store, _, worker = setup()
    job_id = upload(client).json()["id"]
    worker.run(store.get(job_id))
    for rel in ("manifest.json", "../app/" + job_id + ".json", "stems/vocals.wav"):
        assert client.get(f"/jobs/{job_id}/files/{rel}").status_code == 404


def test_transposition_renders_and_caches_complete_band_and_parts(setup):
    client, store, runner, worker = setup()
    job_id = upload(client).json()["id"]
    worker.run(store.get(job_id))
    assert client.post(f"/jobs/{job_id}/transpositions/13").status_code == 422
    assert client.post(f"/jobs/{job_id}/transpositions/-1").status_code == 200
    result = client.get(f"/jobs/{job_id}/transpositions/-1/result").json()
    assert result["semitones"] == -1
    assert set(result["instruments"]) == {"guitar", "bass", "drums", "piano"}
    for part in [result["full_band"], *result["instruments"].values()]:
        for kind in ("pdf", "midi", "mp3"):
            assert client.get(f"/jobs/{job_id}/transpositions/-1/files/{part[kind]}").status_code == 200
    assert client.get(f"/jobs/{job_id}/transpositions/-1/files/manifest.json").status_code == 404
    assert client.post(f"/jobs/{job_id}/transpositions/-1").status_code == 200
    assert len([c for c in runner.calls if c[0] == "transpose"]) == 1


def test_failure_reports_pipeline_error(setup):
    client, store, _, worker = setup(FakeRunner(fail_stage="midi"))
    job_id = upload(client).json()["id"]
    worker.run(store.get(job_id))
    s = client.get(f"/jobs/{job_id}").json()
    assert s["state"] == "failed"
    assert "muscriptor_drums" in s["error"]


def test_pdf_failure_is_a_failed_job(setup):
    client, store, _, worker = setup(FakeRunner(fail_stage="pdf"))
    job_id = upload(client).json()["id"]
    worker.run(store.get(job_id))
    assert client.get(f"/jobs/{job_id}").json()["state"] == "failed"


def test_rerun_skips_finished_midi_stage(setup):
    client, store, runner, worker = setup(FakeRunner(fail_stage="pdf"))
    job_id = upload(client).json()["id"]
    worker.run(store.get(job_id))
    runner.fail_stage = None
    runner.calls.clear()
    worker.run(store.get(job_id))
    assert runner.calls == [("pdf", job_id)]
    assert store.get(job_id).state == "complete"


@pytest.mark.parametrize("name,requested,code", [
    ("song.txt", "piano", 415),
    ("song.wav", "piano,keys", 422),
    ("song.wav", "piano,piano", 422),
])
def test_bad_uploads_are_rejected(setup, name, requested, code):
    client, store, *_ = setup()
    assert upload(client, name=name, requested=requested).status_code == code
    assert store.all() == []


def test_empty_lineup_is_rejected(setup):
    client, store, *_ = setup()
    assert upload(client, requested="").status_code == 422
    assert store.all() == []


@pytest.mark.parametrize("lineup,original,pipe_orig,pipe_req", [
    ("piano,drums,bass,guitar,guitar2", "", "unknown", "keyboard,bass,guitar2,drums"),
    ("piano,guitar", "guitar,drums", "guitar1,drums", "keyboard,guitar1"),
    ("guitar,guitar2", "guitar,guitar2,bass", "bass,guitar2", "guitar2"),
])
def test_pipeline_arguments_from_app_lineup(setup, lineup, original, pipe_orig, pipe_req):
    client, store, runner, worker = setup()
    r = client.post("/jobs", files={"file": ("s.wav", b"RIFF", "audio/wav")},
                    data={"requested": "guitar", "lineup": lineup, "original": original, "title": "t"})
    job = store.get(r.json()["id"])
    assert (job.pipeline_original, job.pipeline_requested) == (pipe_orig, pipe_req)
    worker.run(job)
    assert runner.calls[0][3:] == (pipe_req, pipe_orig)


def test_two_guitars_without_original_guitar_is_rejected(setup):
    client, *_ = setup()
    r = client.post("/jobs", files={"file": ("s.wav", b"RIFF", "audio/wav")},
                    data={"requested": "guitar", "lineup": "guitar,guitar2", "original": "drums,bass"})
    assert r.status_code == 422


def test_api_key(setup):
    client, *_ = setup(key="secret")
    assert upload(client).status_code == 401
    assert upload(client, headers={"X-Rocky-Key": "secret"}).status_code == 201
    assert client.get("/health").status_code == 200


def test_unknown_job_is_404(setup):
    client, *_ = setup()
    assert client.get("/jobs/000000000000").status_code == 404
    assert client.get("/jobs/../etc").status_code == 404


def test_restart_requeues_interrupted_jobs(setup):
    client, store, _, worker = setup()
    job_id = upload(client).json()["id"]
    store.update(store.get(job_id), state="running")
    for t in worker.threads:
        t.run = lambda: None  # start() without a live loop
    worker.start()
    assert store.get(job_id).state == "queued"


def test_complete_job_frees_audio(setup):
    client, store, _, worker = setup()
    job_id = upload(client).json()["id"]
    (store.run_dir(job_id) / "stems").mkdir(parents=True)
    (store.run_dir(job_id) / "stems" / "drums.wav").write_bytes(b"x")
    worker.run(store.get(job_id))
    assert not (store.run_dir(job_id) / "stems").exists()
    assert list(store.inputs.iterdir()) == []
    assert client.get(f"/jobs/{job_id}/files/scores/full_band.pdf").status_code == 200


def test_two_gpus_run_two_songs_at_once(tmp_path, monkeypatch):
    """With ROCKY_PARALLEL=2, two uploads run at the same time; a third waits."""
    import threading
    monkeypatch.setenv("ROCKY_PARALLEL", "2")
    monkeypatch.delenv("ROCKY_API_KEY", raising=False)
    started, release = [], threading.Event()

    class SlowRunner(FakeRunner):
        def run_midi(self, job_id, audio, run, requested, log, note=lambda _m: None, original="unknown"):
            started.append(job_id)
            release.wait(timeout=10)
            super().run_midi(job_id, audio, run, requested, log, note, original)

    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    with TestClient(create_app(store, SlowRunner())) as client:  # starts the workers
        ids = [upload(client).json()["id"] for _ in range(3)]
        for _ in range(100):
            if len(started) == 2:
                break
            threading.Event().wait(0.05)
        assert sorted(started) == sorted(ids[:2])
        assert client.get(f"/jobs/{ids[2]}").json()["queue_position"] == 1
        release.set()
        for _ in range(100):
            if all(store.get(i).state == "complete" for i in ids):
                break
            threading.Event().wait(0.05)
        assert [store.get(i).state for i in ids] == ["complete"] * 3


def test_claim_never_gives_one_job_to_two_workers(setup):
    client, store, _, worker = setup()
    upload(client)
    assert worker.claim() is not None
    assert worker.claim() is None


def test_cancel_queued_job_skips_it_and_keeps_next_song(setup):
    client, store, runner, worker = setup()
    first = upload(client).json()["id"]
    second = upload(client).json()["id"]
    assert client.post(f"/jobs/{first}/cancel").json() == {"id": first, "state": "cancelled"}
    assert client.post(f"/jobs/{first}/cancel").json()["state"] == "cancelled"
    assert client.get(f"/jobs/{first}").json()["state"] == "cancelled"
    assert client.get(f"/jobs/{first}/result").status_code == 409
    assert not (store.inputs / f"{first}.wav").exists()
    assert worker.claim().id == second
    assert ("cancel", first) not in runner.calls  # no Pod was created


def test_cancel_after_claim_cannot_be_revived_by_stale_worker(setup):
    client, store, runner, worker = setup()
    job_id = upload(client).json()["id"]
    stale = worker.claim()
    assert stale.id == job_id
    assert client.post(f"/jobs/{job_id}/cancel").json()["state"] == "cancelling"
    worker.run(stale)
    assert store.get(job_id).state == "cancelled"
    assert not any(call[0] == "midi" for call in runner.calls)


def test_cancel_running_job_stops_it_before_next_song(tmp_path, monkeypatch):
    import threading
    import time
    monkeypatch.delenv("ROCKY_API_KEY", raising=False)
    entered, released = threading.Event(), threading.Event()

    class BlockingRunner(FakeRunner):
        def run_midi(self, job_id, audio, run, requested, log, note=lambda _m: None, original="unknown"):
            if not entered.is_set():
                (run / "stems").mkdir(parents=True)
                (run / "stems" / "drums.wav").write_bytes(b"partial")
                entered.set()
                released.wait(5)
                raise RuntimeError("stopped after cancellation")
            super().run_midi(job_id, audio, run, requested, log, note, original)

        def cancel(self, job_id):
            super().cancel(job_id)
            released.set()

    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    runner = BlockingRunner()
    with TestClient(create_app(store, runner)) as client:
        first = upload(client).json()["id"]
        assert entered.wait(5)
        second = upload(client).json()["id"]
        assert client.get(f"/jobs/{second}").json()["state"] == "queued"
        assert client.post(f"/jobs/{first}/cancel").json()["state"] == "cancelling"
        for _ in range(100):
            if store.get(first).state == "cancelled" and store.get(second).state == "complete":
                break
            time.sleep(0.05)
        assert (store.get(first).state, store.get(second).state) == ("cancelled", "complete")
        assert not store.run_dir(first).exists()
        assert not (store.inputs / f"{first}.wav").exists()
        assert ("cancel", first) in runner.calls


def test_upload_records_original_and_lineup(setup):
    client, store, *_ = setup()
    r = client.post("/jobs", files={"file": ("s.mp3", b"ID3", "audio/mpeg")},
                    data={"requested": "piano,guitar", "original": "guitar,drums,keys",
                          "lineup": "piano,guitar,guitar2", "title": "t"})
    job = store.get(r.json()["id"])
    assert job.original == ["guitar", "drums"]          # unknown names dropped
    assert job.pipeline_original == "guitar1,drums"
    assert job.lineup == ["piano", "guitar", "guitar2"]
    assert job.requested == ["piano", "guitar"]


def test_status_shows_wait_note(setup):
    client, store, *_ = setup()
    job_id = upload(client).json()["id"]
    store.update(store.get(job_id), state="running", note="GPU 차례를 기다리는 중")
    assert client.get(f"/jobs/{job_id}").json()["note"] == "GPU 차례를 기다리는 중"
