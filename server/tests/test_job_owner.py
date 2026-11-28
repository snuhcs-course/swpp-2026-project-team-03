"""Each job records who uploaded it and its mode (beta plan I1), and only that member can put
it in their library (PUT /me/works; PR #55 review item 5)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from rocky_server.accounts import Accounts
from rocky_server.app import create_app
from rocky_server.jobs import JobStore

from fake_pipeline import FakeRunner


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ROCKY_API_KEY", "k")
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    acc = Accounts(store.root / "rocky.db")
    app = create_app(store, FakeRunner(), start_worker=False, accounts=acc)
    c = TestClient(app)
    c.headers["X-Rocky-Key"] = "k"
    return c, store, acc


def sign_up(c, email, nickname, device):
    r = c.post("/auth/signup", json={"email": email, "password": "band2026", "nickname": nickname, "device": device})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["user"]["id"]


def upload(c, headers=None, mode="band", lineup="piano,drums"):
    r = c.post("/jobs", files={"file": ("s.wav", b"RIFF....WAVE", "audio/wav")},
               data={"requested": lineup, "lineup": lineup, "mode": mode}, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def ledger(acc, job_id):
    return acc.db.execute("SELECT user_id, mode FROM experiment_jobs WHERE job_id = ?", (job_id,)).fetchone()


def test_upload_records_the_member_and_the_mode(env):
    c, store, acc = env
    a, a_id = sign_up(c, "a@snu.ac.kr", "에이", "phone-A")
    band = upload(c, a)
    solo = upload(c, a, mode="personal", lineup="drums")
    assert store.get(band).user_id == a_id and store.get(band).mode == "band"
    assert tuple(ledger(acc, band)) == (a_id, "band")
    assert tuple(ledger(acc, solo)) == (a_id, "personal")


def test_upload_without_a_valid_login_still_works_without_an_owner(env):
    c, store, acc = env
    for headers in (None, {"Authorization": "Bearer not-a-token"}):
        job = upload(c, headers)
        assert store.get(job).user_id is None
        assert tuple(ledger(acc, job)) == (None, "band")


def test_owner_can_save_and_another_member_cannot(env):
    c, store, acc = env
    a, _ = sign_up(c, "a@snu.ac.kr", "에이", "phone-A")
    b, _ = sign_up(c, "b@snu.ac.kr", "비비", "phone-B")
    job = upload(c, a)
    assert c.put("/me/works/1", headers=a, json={"job_id": job, "title": "곡"}).status_code == 200
    r = c.put("/me/works/2", headers=b, json={"job_id": job, "title": "곡"})
    assert r.status_code == 403
    assert c.get("/me/works", headers=b).json() == []


def test_a_song_without_an_owner_belongs_to_the_first_member_who_saves_it(env):
    c, store, acc = env
    a, a_id = sign_up(c, "a@snu.ac.kr", "에이", "phone-A")
    b, _ = sign_up(c, "b@snu.ac.kr", "비비", "phone-B")
    job = upload(c)  # an older app sends no login
    assert c.put("/me/works/1", headers=a, json={"job_id": job, "title": "곡"}).status_code == 200
    assert store.get(job).user_id == a_id
    assert ledger(acc, job)["user_id"] == a_id
    # saving again (another phone of the same member) is fine; someone else is refused
    assert c.put("/me/works/1", headers=a, json={"job_id": job, "title": "곡"}).status_code == 200
    assert c.put("/me/works/9", headers=b, json={"job_id": job, "title": "곡"}).status_code == 403


def test_owner_is_kept_when_the_job_state_changes(env):
    c, store, acc = env
    a, a_id = sign_up(c, "a@snu.ac.kr", "에이", "phone-A")
    job = store.get(upload(c, a))
    store.update(job, state="failed", error_code="pipeline_error")
    assert store.get(job.id).user_id == a_id
    assert ledger(acc, job.id)["user_id"] == a_id


def test_older_database_gets_the_new_columns(tmp_path):
    path = tmp_path / "rocky.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE experiment_jobs (job_id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at REAL NOT NULL,"
               " started_at REAL, finished_at REAL, processing_seconds REAL, failure_code TEXT,"
               " rejection_reason TEXT, assigned_model TEXT, applied_model TEXT, model_sha256 TEXT,"
               " model_manifest_sha256 TEXT, assignment_probability REAL, predicted_guitars INTEGER,"
               " experiment_eligible INTEGER)")
    db.execute("INSERT INTO experiment_jobs (job_id, state, created_at) VALUES ('0123456789ab', 'complete', 1)")
    db.commit()
    db.close()
    acc = Accounts(path)
    cols = {r["name"] for r in acc.db.execute("PRAGMA table_info(experiment_jobs)")}
    assert {"user_id", "mode"} <= cols
    assert tuple(ledger(acc, "0123456789ab")) == (None, None)
