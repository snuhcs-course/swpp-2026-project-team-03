"""Listening MP3s are kept for a day after a song finishes (beta storage); PDF and MIDI stay."""
import time

from test_api import setup, upload  # noqa: F401  (pytest fixture)

from rocky_server.jobs import audio_expires_at, drop_expired_audio


def finished(client, store, worker):
    job_id = upload(client).json()["id"]
    worker.run(store.get(job_id))
    return job_id


def age(store, job_id, seconds):
    job = store.get(job_id)
    store.update(job, finished_at=time.time() - seconds)


def test_fresh_song_lists_mp3_and_tells_when_it_expires(setup):
    client, store, _, worker = setup()
    job_id = finished(client, store, worker)
    result = client.get(f"/jobs/{job_id}/result").json()
    assert result["full_band"]["mp3"] == "scores/band.mp3"
    finished_at = store.get(job_id).finished_at
    assert abs(result["audio_expires_at"] - (finished_at + 86400)) < 1
    assert client.get(f"/jobs/{job_id}/files/scores/band.mp3").status_code == 200


def test_after_a_day_mp3_is_hidden_and_deleted_but_scores_stay(setup):
    client, store, _, worker = setup()
    job_id = finished(client, store, worker)
    age(store, job_id, 86400 + 5)
    result = client.get(f"/jobs/{job_id}/result").json()
    assert all("mp3" not in part for part in [result["full_band"], *result["instruments"].values()])
    assert client.get(f"/jobs/{job_id}/files/scores/band.mp3").status_code == 404
    assert drop_expired_audio(store) == [job_id]
    run = store.run_dir(job_id)
    assert not list(run.rglob("*.mp3"))
    assert (run / "scores" / "full_band.pdf").is_file() and (run / "scores" / "guitar.mid").is_file()
    assert client.get(f"/jobs/{job_id}/files/scores/full_band.pdf").status_code == 200
    assert client.get(f"/jobs/{job_id}/files/scores/guitar.mid").status_code == 200
    assert drop_expired_audio(store) == []  # nothing left to delete


def test_fresh_songs_keep_their_mp3(setup):
    client, store, _, worker = setup()
    job_id = finished(client, store, worker)
    age(store, job_id, 86400 - 60)
    assert drop_expired_audio(store) == []
    assert list(store.run_dir(job_id).rglob("*.mp3"))


def test_transposed_mp3_expires_with_the_song(setup):
    client, store, _, worker = setup()
    job_id = finished(client, store, worker)
    assert client.post(f"/jobs/{job_id}/transpositions/2").status_code == 202
    for _ in range(100):
        if client.get(f"/jobs/{job_id}/transpositions/2").json()["state"] == "complete":
            break
        time.sleep(.02)
    assert "mp3" in client.get(f"/jobs/{job_id}/transpositions/2/result").json()["full_band"]
    age(store, job_id, 86400 + 5)
    result = client.get(f"/jobs/{job_id}/transpositions/2/result").json()
    assert "mp3" not in result["full_band"] and result["audio_expires_at"] is not None
    drop_expired_audio(store)
    assert not list((store.run_dir(job_id) / "transpositions").rglob("*.mp3"))
    assert client.get(f"/jobs/{job_id}/transpositions/2/result").status_code == 200


def test_ttl_zero_keeps_mp3_forever(setup, monkeypatch):
    client, store, _, worker = setup()
    monkeypatch.setenv("ROCKY_AUDIO_TTL_SEC", "0")
    job_id = finished(client, store, worker)
    age(store, job_id, 10 * 86400)
    assert audio_expires_at(store.get(job_id)) is None
    assert client.get(f"/jobs/{job_id}/result").json()["full_band"]["mp3"] == "scores/band.mp3"
    assert drop_expired_audio(store) == []


def test_unfinished_songs_are_never_touched(setup):
    client, store, _, worker = setup()
    job_id = upload(client).json()["id"]
    assert audio_expires_at(store.get(job_id)) is None
    assert drop_expired_audio(store, now=time.time() + 10 * 86400) == []
