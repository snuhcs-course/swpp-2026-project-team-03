"""One phone per account, and the library (보관함) kept on the server for every phone."""

import pytest
from fastapi.testclient import TestClient

from rocky_server import accounts as accounts_module
from rocky_server.accounts import Accounts
from rocky_server.app import create_app
from rocky_server.jobs import JobStore

from fake_pipeline import FakeRunner

DAY = 86_400_000


class Clock:
    def __init__(self):
        self.t = 1_795_000_000_000

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ROCKY_API_KEY", "k")
    clock = Clock()
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    acc = Accounts(store.root / "rocky.db", clock=clock)
    app = create_app(store, FakeRunner(), start_worker=False, accounts=acc)
    c = TestClient(app)
    c.headers["X-Rocky-Key"] = "k"
    return c, store, acc, clock


def sign_up(c, device="phone-A", email="a@snu.ac.kr", nickname="에이"):
    r = c.post("/auth/signup", json={"email": email, "password": "band2026", "nickname": nickname, "device": device})
    assert r.status_code == 201, r.text
    return r.json()


def login(c, device, email="a@snu.ac.kr", force=False):
    return c.post("/auth/login", json={"email": email, "password": "band2026", "device": device, "force": force})


def auth(s):
    return {"Authorization": "Bearer " + s["token"]}


def done_job(store, title="곡"):
    job = store.create(title, "", ["guitar"])
    store.update(job, state="complete")
    return job


# ---------- one phone per account ----------

def test_second_phone_is_warned_first(env):
    c, *_ = env
    a = sign_up(c, "phone-A")
    r = login(c, "phone-B")
    assert r.status_code == 409 and r.json()["field"] == "session"
    assert r.json()["detail"] == "다른 핸드폰에서 로그인중입니다. 돌리고 있는 곡이 있으면 취소됩니다"
    assert c.get("/me", headers=auth(a)).status_code == 200  # phone A is untouched until confirmed


def test_confirming_the_warning_moves_the_account_to_the_new_phone(env):
    c, *_ = env
    a = sign_up(c, "phone-A")
    b = login(c, "phone-B", force=True)
    assert b.status_code == 200
    gone = c.get("/me", headers=auth(a))
    assert gone.status_code == 401 and gone.json()["detail"] == "login required"  # phone A logs itself out
    assert c.get("/me", headers=auth(b.json())).status_code == 200
    assert login(c, "phone-A").status_code == 409  # and phone A is warned the same way


def test_force_needs_the_right_password(env):
    c, *_ = env
    a = sign_up(c, "phone-A")
    r = c.post("/auth/login", json={"email": "a@snu.ac.kr", "password": "wrong999", "device": "B", "force": True})
    assert r.status_code == 401
    assert c.get("/me", headers=auth(a)).status_code == 200


def test_wrong_password_is_still_401_not_a_session_hint(env):
    c, *_ = env
    sign_up(c, "phone-A")
    r = c.post("/auth/login", json={"email": "a@snu.ac.kr", "password": "wrong999", "device": "phone-B"})
    assert r.status_code == 401


def test_after_logout_another_phone_can_log_in(env):
    c, *_ = env
    a = sign_up(c, "phone-A")
    c.post("/auth/logout", headers=auth(a))
    assert login(c, "phone-B").status_code == 200
    assert login(c, "phone-A").status_code == 409  # now phone B holds the account


def test_same_phone_logs_in_again_after_a_reinstall(env):
    c, *_ = env
    a = sign_up(c, "phone-A")  # the app was deleted without logging out; the token is lost
    again = login(c, "phone-A")
    assert again.status_code == 200
    assert c.get("/me", headers=auth(a)).status_code == 401  # the old token is gone
    assert c.get("/me", headers=auth(again.json())).status_code == 200


def test_a_phone_unused_for_long_no_longer_blocks(env, monkeypatch):
    c, _, _, clock = env
    monkeypatch.setattr(accounts_module, "SESSION_IDLE_DAYS", 14)
    a = sign_up(c, "phone-A")
    clock.t += 13 * DAY
    assert c.get("/me", headers=auth(a)).status_code == 200  # using the app keeps the session fresh
    clock.t += 13 * DAY
    assert login(c, "phone-B").status_code == 409
    clock.t += 15 * DAY
    b = login(c, "phone-B")
    assert b.status_code == 200
    assert c.get("/me", headers=auth(a)).status_code == 401  # phone A is logged out


def test_older_app_sessions_never_block_but_are_blocked(env):
    c, _, acc, _ = env
    old = c.post("/auth/signup", json={"email": "a@snu.ac.kr", "password": "band2026", "nickname": "에이"}).json()
    b = login(c, "phone-B")  # an app without a device id does not hold the account
    assert b.status_code == 200
    assert c.get("/me", headers=auth(old)).status_code == 401
    # but an older app cannot log in while a phone with the new app is logged in
    assert c.post("/auth/login", json={"email": "a@snu.ac.kr", "password": "band2026"}).status_code == 409


def test_sessions_from_before_the_update_do_not_lock_anyone_out(tmp_path):
    import sqlite3
    db = tmp_path / "rocky.db"
    acc = Accounts(db)
    acc.sign_up("a@snu.ac.kr", "band2026", "에이", [])
    acc.db.close()
    raw = sqlite3.connect(db)  # an older server: sessions without the new columns
    raw.execute("CREATE TABLE s2 AS SELECT token_hash, user_id, created_at FROM sessions")
    raw.execute("DROP TABLE sessions")
    raw.execute("ALTER TABLE s2 RENAME TO sessions")
    raw.commit()
    raw.close()
    again = Accounts(db)
    assert again.login("a@snu.ac.kr", "band2026", "phone-B") is not None


# ---------- library on the server ----------

def test_library_follows_the_account_to_another_phone(env):
    c, store, *_ = env
    a = sign_up(c, "phone-A")
    job = done_job(store, "Don't Look Back")
    r = c.put("/me/works/1700000000001", headers=auth(a), json={
        "job_id": job.id, "title": "Don't Look Back", "instruments": ["piano", "guitar", "guitar2", "kazoo"],
        "date": "2026.11.26", "original": ["guitar"], "unrecognized": [], "personal": False})
    assert r.status_code == 200, r.text
    c.post("/auth/logout", headers=auth(a))

    b = login(c, "phone-B").json()
    works = c.get("/me/works", headers=auth(b)).json()
    assert len(works) == 1
    w = works[0]
    assert (w["work_id"], w["job_id"], w["title"]) == (1700000000001, job.id, "Don't Look Back")
    assert w["instruments"] == ["piano", "guitar", "guitar2"] and w["original"] == ["guitar"]
    assert w["personal"] is False


def test_library_is_per_member(env):
    c, store, *_ = env
    a = sign_up(c, "phone-A")
    b = sign_up(c, "phone-B", email="b@snu.ac.kr", nickname="비비")
    job = done_job(store)
    c.put("/me/works/1", headers=auth(a), json={"job_id": job.id, "title": "곡"})
    assert c.get("/me/works", headers=auth(b)).json() == []
    assert c.get("/me/works").status_code == 401


def test_save_is_idempotent_rename_and_delete(env):
    c, store, *_ = env
    a = sign_up(c)
    job = done_job(store)
    for _ in range(2):
        c.put("/me/works/7", headers=auth(a), json={"job_id": job.id, "title": "곡", "personal": True})
    assert len(c.get("/me/works", headers=auth(a)).json()) == 1
    c.patch("/me/works/7", headers=auth(a), json={"title": "새 이름"})
    assert c.get("/me/works", headers=auth(a)).json()[0]["title"] == "새 이름"
    assert c.delete("/me/works/7", headers=auth(a)).json() == {"deleted": True}
    assert c.get("/me/works", headers=auth(a)).json() == []


def test_save_rejects_bad_or_missing_jobs(env):
    c, store, *_ = env
    a = sign_up(c)
    assert c.put("/me/works/1", headers=auth(a), json={"job_id": "nope", "title": "곡"}).status_code == 422
    assert c.put("/me/works/1", headers=auth(a), json={"job_id": "0123456789ab", "title": "곡"}).status_code == 404
    job = done_job(store)
    assert c.put("/me/works/1", headers=auth(a), json={"job_id": job.id, "title": " "}).status_code == 422


def test_deleting_the_song_removes_it_from_the_library(env):
    c, store, *_ = env
    a = sign_up(c)
    job = done_job(store)
    c.put("/me/works/1", headers=auth(a), json={"job_id": job.id, "title": "곡"})
    assert c.delete(f"/jobs/{job.id}").status_code == 200
    assert c.get("/me/works", headers=auth(a)).json() == []
