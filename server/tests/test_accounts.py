"""Members, bands and shared scores on the server (two phones in one band)."""

import pytest
from fastapi.testclient import TestClient

from rocky_server.accounts import OLD_DEMO_CODE, Accounts, hash_password, verify_password
from rocky_server.app import create_app
from rocky_server.jobs import JobStore

from fake_pipeline import FakeRunner


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROCKY_API_KEY", "k")
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    app = create_app(store, FakeRunner(), start_worker=False)
    c = TestClient(app)
    c.headers["X-Rocky-Key"] = "k"
    c.app_state = app.state
    return c


def sign_up(c, email="rocky@snu.ac.kr", nickname="락스타", password="band2026", instruments=("guitar",)):
    r = c.post("/auth/signup", json={"email": email, "password": password, "nickname": nickname,
                                     "instruments": list(instruments)})
    assert r.status_code == 201, r.text
    return r.json()


def auth(s):
    return {"Authorization": "Bearer " + s["token"]}


def test_password_hash_matches_app_format():
    h = hash_password("band2026", iterations=1000)
    assert h.startswith("pbkdf2-sha256$1000$")
    assert verify_password("band2026", h) and not verify_password("band2027", h)
    # made by the app's PasswordHasher (PBKDF2WithHmacSHA256, 1000 rounds)
    assert not verify_password("x", "plain") and not verify_password("x", None)


def test_sign_up_login_and_profile(client):
    s = sign_up(client, email=" Rocky@SNU.ac.kr", instruments=["guitar", "drums", "kazoo"])
    assert s["user"]["email"] == "rocky@snu.ac.kr"
    assert s["user"]["instruments"] == ["drums", "guitar"]
    assert client.get("/me", headers=auth(s)).json()["nickname"] == "락스타"

    dup = client.post("/auth/signup", json={"email": "rocky@snu.ac.kr", "password": "band2026", "nickname": "다른"})
    assert (dup.status_code, dup.json()["field"]) == (409, "email")
    dup = client.post("/auth/signup", json={"email": "b@snu.ac.kr", "password": "band2026", "nickname": "락스타"})
    assert (dup.status_code, dup.json()["field"]) == (409, "nickname")
    bad = client.post("/auth/signup", json={"email": "b@snu.ac.kr", "password": "short", "nickname": "beta"})
    assert (bad.status_code, bad.json()["field"]) == (422, "password")

    assert client.get("/auth/taken", params={"email": "ROCKY@snu.ac.kr"}).json() == {"taken": True}
    assert client.get("/auth/taken", params={"nickname": "락스타"}).json() == {"taken": True}
    assert client.get("/auth/taken", params={"nickname": "락스타"}, headers=auth(s)).json() == {"taken": False}

    wrong = client.post("/auth/login", json={"email": "rocky@snu.ac.kr", "password": "band2027"})
    unknown = client.post("/auth/login", json={"email": "no@snu.ac.kr", "password": "band2026"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
    again = client.post("/auth/login", json={"email": "ROCKY@snu.ac.kr ", "password": "band2026"}).json()
    assert again["user"]["id"] == s["user"]["id"] and again["token"] != s["token"]

    me = client.patch("/me", json={"nickname": "베이시스트", "instruments": ["bass"]}, headers=auth(again)).json()
    assert (me["nickname"], me["instruments"]) == ("베이시스트", ["bass"])

    client.post("/auth/logout", headers=auth(again))
    assert client.get("/me", headers=auth(again)).status_code == 401
    assert client.get("/me", headers=auth(s)).status_code == 200  # the other phone stays logged in


def test_app_key_and_login_are_required(client):
    assert client.get("/bands").status_code == 401
    assert client.get("/bands", headers={"X-Rocky-Key": "wrong", "Authorization": "Bearer x"}).status_code == 401
    assert client.get("/bands", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_two_phones_share_a_band(client):
    a = sign_up(client)
    b = sign_up(client, email="drum@snu.ac.kr", nickname="드러머", instruments=["drums"])

    band = client.post("/bands", json={"name": " 우리 밴드 ", "instrument": "guitar"}, headers=auth(a)).json()
    assert band["name"] == "우리 밴드" and len(band["invite_code"]) == 6
    code = band["invite_code"][:3] + "-" + band["invite_code"][3:].lower()
    assert client.post("/bands/join", json={"code": code, "instrument": "drums"}, headers=auth(b)).status_code == 200
    again = client.post("/bands/join", json={"code": code, "instrument": "drums"}, headers=auth(b))
    assert again.status_code == 409
    assert client.post("/bands/join", json={"code": "ZZZZZZ", "instrument": "bass"}, headers=auth(b)).status_code == 404

    shared = client.post(f"/bands/{band['id']}/scores", headers=auth(a), json={
        "work_id": 9000000000001, "job_id": "abc123abc123", "title": "Immigrant Song",
        "instruments": ["guitar", "drums"], "date": "2026.11.09 10:00", "original": ["guitar"]}).json()
    assert shared == {"created": True}
    assert client.post(f"/bands/{band['id']}/scores", headers=auth(a),
                       json={"work_id": 9000000000001, "title": "x"}).json() == {"created": False}

    # the drummer's phone sees the members and the score, with the server job to download
    d = client.get(f"/bands/{band['id']}", headers=auth(b)).json()
    assert [(m["nickname"], m["instrument"], m["is_owner"]) for m in d["members"]] == [
        ("락스타", "guitar", True), ("드러머", "drums", False)]
    assert [(s["title"], s["job_id"], s["shared_by_name"]) for s in d["scores"]] == [
        ("Immigrant Song", "abc123abc123", "락스타")]
    summary = client.get("/bands", headers=auth(b)).json()
    assert [(x["band"]["id"], x["member_count"], x["score_count"], x["my_instrument"]) for x in summary] == [
        (band["id"], 2, 1, "drums")]

    # a nickname change shows in the band right away
    client.patch("/me", json={"nickname": "기타리스트", "instruments": ["guitar"]}, headers=auth(a))
    d = client.get(f"/bands/{band['id']}", headers=auth(b)).json()
    assert d["members"][0]["nickname"] == d["scores"][0]["shared_by_name"] == "기타리스트"

    # only the owner renames the band; the sharer or the owner renames a score
    assert client.patch(f"/bands/{band['id']}", json={"name": "새 이름"}, headers=auth(b)).status_code == 403
    assert client.patch(f"/bands/{band['id']}", json={"name": "새 이름"}, headers=auth(a)).json()["name"] == "새 이름"
    sid = d["scores"][0]["id"]
    assert client.patch(f"/bands/{band['id']}/scores/{sid}", json={"title": "y"}, headers=auth(b)).status_code == 403
    client.patch("/me/works/9000000000001", json={"title": "Immigrant Song (live)"}, headers=auth(a))
    assert client.get(f"/bands/{band['id']}", headers=auth(b)).json()["scores"][0]["title"] == "Immigrant Song (live)"
    assert client.get("/me/works/9000000000001/shared", headers=auth(a)).json() == {"shared": True}
    assert client.get("/me/works/9000000000001/shared", headers=auth(b)).json() == {"shared": False}

    # the owner leaves: the drummer becomes owner; the last member leaves: the band is gone
    client.post(f"/bands/{band['id']}/leave", headers=auth(a))
    assert client.get(f"/bands/{band['id']}", headers=auth(a)).status_code == 403
    d = client.get(f"/bands/{band['id']}", headers=auth(b)).json()
    assert d["band"]["owner_id"] == b["user"]["id"]
    client.post(f"/bands/{band['id']}/leave", headers=auth(b))
    assert client.get(f"/bands/{band['id']}", headers=auth(b)).status_code == 404


def test_outsiders_cannot_read_or_share(client):
    a = sign_up(client)
    c = sign_up(client, email="c@snu.ac.kr", nickname="남남")
    band = client.post("/bands", json={"name": "밴드", "instrument": "guitar"}, headers=auth(a)).json()
    assert client.get(f"/bands/{band['id']}", headers=auth(c)).status_code == 403
    r = client.post(f"/bands/{band['id']}/scores", json={"work_id": 1, "title": "t"}, headers=auth(c))
    assert r.status_code == 403
    r = client.post(f"/bands/{band['id']}/scores", json={"work_id": 1, "title": "t", "job_id": "../x"},
                    headers=auth(a))
    assert r.status_code == 422
    assert client.post("/bands", json={"name": "", "instrument": "guitar"}, headers=auth(a)).status_code == 422
    assert client.post("/bands", json={"name": "a" * 21, "instrument": "guitar"}, headers=auth(a)).status_code == 422
    assert client.post("/bands", json={"name": "x", "instrument": "kazoo"}, headers=auth(a)).status_code == 422


def test_a_band_has_at_most_eight_members(client):
    owner = sign_up(client, "owner@snu.ac.kr", "방장")
    band = client.post("/bands", json={"name": "꽉 찬 밴드", "instrument": "guitar"}, headers=auth(owner)).json()
    for i in range(7):
        s = sign_up(client, f"m{i}@snu.ac.kr", f"멤버{i}")
        r = client.post("/bands/join", json={"code": band["invite_code"], "instrument": "drums"}, headers=auth(s))
        assert r.status_code == 200
    ninth = sign_up(client, "late@snu.ac.kr", "늦은멤버")
    r = client.post("/bands/join", json={"code": band["invite_code"], "instrument": "bass"}, headers=auth(ninth))
    assert r.status_code == 409 and "최대 8명" in r.json()["detail"]


def test_there_is_no_demo_band(client):
    # the demo band (and its demo song that lived only inside the app) was removed on 2026-11-11
    a = sign_up(client)
    r = client.post("/bands/join", json={"code": OLD_DEMO_CODE.lower(), "instrument": "bass"}, headers=auth(a))
    assert r.status_code == 404
    assert client.get("/bands", headers=auth(a)).json() == []


def test_old_demo_band_is_removed_from_an_existing_database(tmp_path):
    import sqlite3
    db = tmp_path / "rocky.db"
    acc = Accounts(db)
    real, _ = acc.sign_up("a@snu.ac.kr", "band2026", "에이", ["piano"])
    acc.create_band(real, "밴드", "piano")
    # what an older server had seeded: members without a password, their band and the demo song
    t = 1_793_350_000_000
    ids = [acc.db.execute("INSERT INTO users (email, nickname, instruments, terms_agreed_at, created_at)"
                          " VALUES (?, ?, 'guitar', ?, ?)", (f"demo{i}@rocky.invalid", f"데모{i}", t, t)).lastrowid
           for i in (1, 2, 3)]
    band = acc.db.execute("INSERT INTO bands (name, invite_code, owner_id, created_at) VALUES ('소개원실 밴드', ?, ?, ?)",
                          (OLD_DEMO_CODE, ids[0], t)).lastrowid
    for uid in ids:
        acc.db.execute("INSERT INTO band_members VALUES (?, ?, 'guitar', ?)", (band, uid, t))
    acc.db.execute("INSERT INTO band_members VALUES (?, ?, 'piano', ?)", (band, real.id, t))  # a real user joined it
    acc.db.execute("INSERT INTO shared_scores (band_id, work_id, job_id, title, instruments, work_date, original,"
                   " shared_by, shared_at) VALUES (?, 1, NULL, '데모 곡', 'piano', '', '', ?, ?)", (band, ids[0], t))
    acc.db.close()

    again = Accounts(db)
    count = lambda sql, *a: again.db.execute(sql, a).fetchone()[0]
    assert count("SELECT COUNT(*) FROM bands WHERE invite_code = ?", OLD_DEMO_CODE) == 0
    assert count("SELECT COUNT(*) FROM users WHERE email LIKE '%@rocky.invalid'") == 0
    assert count("SELECT COUNT(*) FROM shared_scores") == 0
    # the real member and their own band stay
    assert again.login("a@snu.ac.kr", "band2026")[0].id == real.id
    assert [b["band"]["name"] for b in again.bands_of(real)] == ["밴드"]
    sqlite3.connect(db).close()


def test_shared_job_is_not_deleted(client):
    store = client.app_state.store
    job = store.create("t", "", ["guitar"])
    store.update(job, state="complete")
    a = sign_up(client)
    band = client.post("/bands", json={"name": "밴드", "instrument": "guitar"}, headers=auth(a)).json()
    client.post(f"/bands/{band['id']}/scores", json={"work_id": 5, "job_id": job.id, "title": "t"}, headers=auth(a))
    assert client.delete(f"/jobs/{job.id}").status_code == 409
    assert store.get(job.id) is not None
    client.post(f"/bands/{band['id']}/leave", headers=auth(a))  # the band and its scores are gone
    assert client.delete(f"/jobs/{job.id}").status_code == 200


def test_personal_scores_are_not_shared_to_a_band(client):
    store = client.app_state.store
    solo = store.create("혼자 연습", "", ["bass"], mode="personal")
    store.update(solo, state="complete")
    a = sign_up(client)
    band = client.post("/bands", json={"name": "밴드", "instrument": "bass"}, headers=auth(a)).json()
    r = client.post(f"/bands/{band['id']}/scores", json={"work_id": 9, "job_id": solo.id, "title": "t"}, headers=auth(a))
    assert r.status_code == 409
    assert client.get(f"/bands/{band['id']}", headers=auth(a)).json()["scores"] == []


def test_data_survives_a_restart(tmp_path):
    db = tmp_path / "rocky.db"
    acc = Accounts(db)
    user, _ = acc.sign_up("a@snu.ac.kr", "band2026", "에이", ["piano"])
    acc.create_band(user, "밴드", "piano")
    acc.db.close()
    again = Accounts(db)
    assert again.login("a@snu.ac.kr", "band2026")[0].id == user.id
    assert [b["band"]["name"] for b in again.bands_of(user)] == ["밴드"]
    assert again.db.execute("SELECT COUNT(*) FROM bands").fetchone()[0] == 1
