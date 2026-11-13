"""Star ratings the app sends from under the last score page (PUT /jobs/{id}/rating, GET /ratings)."""

from test_accounts import auth, client, sign_up  # noqa: F401  (client is a fixture)


def finished_job(c):
    store = c.app_state.store
    job = store.create("Basket Case", "", ["drums", "guitar"])
    store.update(job, state="complete")
    return job.id


def test_rating_is_saved_and_listed(client):  # noqa: F811
    job = finished_job(client)
    r = client.put(f"/jobs/{job}/rating", json={"stars": 4, "title": "Basket Case", "instruments": ["drums", "guitar", "kazoo"]})
    assert r.status_code == 200 and r.json() == {"job_id": job, "stars": 4}
    summary = client.get("/ratings").json()
    assert summary["count"] == 1 and summary["average"] == 4.0
    assert summary["histogram"]["4"] == 1
    item = summary["ratings"][0]
    assert (item["job_id"], item["stars"], item["title"]) == (job, 4, "Basket Case")
    assert item["instruments"] == ["drums", "guitar"]  # unknown names are dropped
    assert item["logged_in"] is False


def test_rating_again_changes_it(client):  # noqa: F811
    job = finished_job(client)
    client.put(f"/jobs/{job}/rating", json={"stars": 2})
    client.put(f"/jobs/{job}/rating", json={"stars": 5})
    summary = client.get("/ratings").json()
    assert summary["count"] == 1 and summary["ratings"][0]["stars"] == 5


def test_each_member_rates_separately(client):  # noqa: F811
    job = finished_job(client)
    a = sign_up(client)
    b = sign_up(client, email="b@snu.ac.kr", nickname="베이스")
    client.put(f"/jobs/{job}/rating", json={"stars": 5}, headers=auth(a))
    client.put(f"/jobs/{job}/rating", json={"stars": 3}, headers=auth(b))
    summary = client.get("/ratings").json()
    assert summary["count"] == 2 and summary["average"] == 4.0
    assert all(i["logged_in"] for i in summary["ratings"])


def test_bad_ratings_are_refused(client):  # noqa: F811
    job = finished_job(client)
    for stars in (0, 6, "5", None, True, 4.5):
        assert client.put(f"/jobs/{job}/rating", json={"stars": stars}).status_code == 422
    assert client.put("/jobs/000000000000/rating", json={"stars": 3}).status_code == 404
    assert client.put("/jobs/../x/rating", json={"stars": 3}).status_code == 404
    assert client.get("/ratings").json()["count"] == 0


def test_rating_needs_the_api_key(client):  # noqa: F811
    job = finished_job(client)
    del client.headers["X-Rocky-Key"]
    assert client.get("/ratings").status_code == 401
    assert client.put(f"/jobs/{job}/rating", json={"stars": 3}).status_code == 401


def test_popup_comment_is_saved_and_kept_when_only_stars_change(client):  # noqa: F811
    job = finished_job(client)
    r = client.put(f"/jobs/{job}/rating", json={"stars": 3, "comment": "  베이스가\n좀 틀려요  "})
    assert r.status_code == 200
    assert client.get("/ratings").json()["ratings"][0]["comment"] == "베이스가 좀 틀려요"
    client.put(f"/jobs/{job}/rating", json={"stars": 4})          # stars under the last page: no comment
    item = client.get("/ratings").json()["ratings"][0]
    assert (item["stars"], item["comment"]) == (4, "베이스가 좀 틀려요")
    client.put(f"/jobs/{job}/rating", json={"stars": 4, "comment": ""})  # cleared in the popup
    assert client.get("/ratings").json()["ratings"][0]["comment"] == ""
    assert client.put(f"/jobs/{job}/rating", json={"stars": 4, "comment": 7}).status_code == 422


def test_old_ratings_table_gets_the_comment_column(tmp_path):
    import sqlite3
    from rocky_server.accounts import Accounts
    path = tmp_path / "accounts.db"
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE ratings (job_id TEXT NOT NULL, rater INTEGER NOT NULL DEFAULT 0,
                  stars INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '', instruments TEXT NOT NULL DEFAULT '',
                  rated_at INTEGER NOT NULL, PRIMARY KEY (job_id, rater))""")
    db.execute("INSERT INTO ratings VALUES ('abc', 0, 5, 't', '', 1)")
    db.commit()
    db.close()
    accounts = Accounts(path)
    assert accounts.ratings()["ratings"][0]["comment"] == ""
    accounts.rate("abc", 2, None, comment="좋아요")
    assert accounts.ratings()["ratings"][0]["comment"] == "좋아요"
