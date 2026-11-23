"""Songs the app stopped asking about leave the queue (2nd UAT: the phone lost the internet)."""
import time

from fastapi.testclient import TestClient

from fake_pipeline import FakeRunner
from rocky_server.app import create_app
from rocky_server.jobs import JobStore, Worker


def upload(client):
    response = client.post("/jobs", files={"file": ("song.wav", b"RIFFaudio", "audio/wav")},
                           data={"requested": "guitar"})
    assert response.status_code == 201
    return response.json()["id"]


def make(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    app = create_app(store, FakeRunner(), start_worker=False)
    return store, app.state.worker, TestClient(app)


def test_queued_song_nobody_asks_about_is_cancelled(tmp_path):
    store, worker, client = make(tmp_path)
    job_id = upload(client)
    assert store.get(job_id).state == "queued"
    later = time.time() + worker.abandon_sec + 1
    assert worker.drop_abandoned(now=later) == [job_id]
    body = client.get(f"/jobs/{job_id}").json()
    assert body["state"] == "cancelled"
    assert body["queue_position"] is None
    assert worker.claim() is None  # it never runs


def test_song_the_app_keeps_polling_stays(tmp_path):
    store, worker, client = make(tmp_path)
    job_id = upload(client)
    client.get(f"/jobs/{job_id}")  # the app asks again
    assert worker.drop_abandoned(now=time.time() + worker.abandon_sec - 5) == []
    assert store.get(job_id).state == "queued"


def test_running_song_is_stopped(tmp_path):
    store, worker, client = make(tmp_path)
    job_id = upload(client)
    assert worker.claim().id == job_id  # now running on a GPU
    assert worker.drop_abandoned(now=time.time() + worker.abandon_sec + 1) == [job_id]
    assert store.get(job_id).state == "cancelling"


def test_finished_songs_and_unwatched_songs_are_left_alone(tmp_path):
    store, worker, client = make(tmp_path)
    done = upload(client)
    store.update(store.get(done), state="complete")
    old = store.create("from before the restart", "", ["guitar"])
    store.update(old, state="queued")
    assert worker.drop_abandoned(now=time.time() + 10_000) == []
    assert store.get(done).state == "complete"
    assert store.get(old.id).state == "queued"
    assert done not in worker.last_seen  # forgotten once settled


def test_zero_turns_it_off(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    worker = Worker(store, FakeRunner(), abandon_sec=0)
    job = store.create("song", "", ["guitar"])
    store.update(job, state="queued")
    worker.seen(job.id, now=0)
    assert worker.drop_abandoned(now=10_000) == []
    assert store.get(job.id).state == "queued"
