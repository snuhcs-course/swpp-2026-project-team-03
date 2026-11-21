"""Alpha denominators include unrated and failed jobs, but honor song deletion."""

import json

import pytest
from fastapi.testclient import TestClient

from rocky_server.app import create_app
from rocky_server.jobs import JobStore, Worker
from rocky_server.rating_model import rating_model
from test_accounts import client  # noqa: F401 - pytest fixture
from fake_pipeline import FakeRunner


def manifest(store, job_id, arm, *, result=None, status="running"):
    run = store.run_dir(job_id)
    run.mkdir(parents=True, exist_ok=True)
    data = {"status": status, "config": {
        "guitar_count_classifier": "alpha_three_arm", "guitar_count_arm": arm,
        "guitar_count_arm_probability": 1 / 3,
        "guitar_count_alpha_manifest_sha256": "a" * 64}}
    if result is not None:
        data["guitar_count"] = result
    (run / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


def row(accounts, job_id):
    return accounts.db.execute("SELECT * FROM experiment_jobs WHERE job_id = ?", (job_id,)).fetchone()


def test_unrated_failed_job_keeps_assignment_until_deletion(client):  # noqa: F811
    store, accounts = client.app_state.store, client.app_state.accounts
    job = store.create("failure", "", ["guitar"])
    assert row(accounts, job.id)["assigned_model"] is None
    manifest(store, job.id, "fusion_extra_trees")
    store.update(job, state="running", started_at=1000.0)
    store.update(job, state="failed", finished_at=1025.0, error_code="pipeline_error")
    saved = row(accounts, job.id)
    assert (saved["state"], saved["assigned_model"], saved["failure_code"]) == (
        "failed", "fusion_extra_trees", "pipeline_error")
    assert saved["assignment_probability"] == 1 / 3
    assert saved["model_manifest_sha256"] == "a" * 64
    assert saved["processing_seconds"] == 25.0
    assert accounts.ratings()["count"] == 0
    store.purge(job.id)
    assert row(accounts, job.id) is None


def test_completed_job_and_rating_join_by_job_id(client):  # noqa: F811
    store, accounts = client.app_state.store, client.app_state.accounts
    job = store.create("finished", "", ["guitar"])
    arm = "fusion_rbf_svm"
    manifest(store, job.id, arm, status="complete", result={
        "method": "alpha_three_arm", "assigned_arm": arm, "experiment_eligible": True,
        "assignment_probability": 1 / 3, "model_sha256": "b" * 64, "count": 2})
    store.update(job, state="complete", started_at=2000.0, finished_at=2050.0)
    assert row(accounts, job.id)["experiment_eligible"] == 1
    assert row(accounts, job.id)["processing_seconds"] == 50.0
    assert accounts.ratings()["count"] == 0  # this completed job is in the denominator already
    assert client.put(f"/jobs/{job.id}/rating", json={"stars": 4}).status_code == 200
    joined = accounts.db.execute("""SELECT e.assigned_model, e.state, e.processing_seconds, r.stars
                                    FROM experiment_jobs e JOIN ratings r USING(job_id)
                                    WHERE e.job_id = ?""", (job.id,)).fetchone()
    assert tuple(joined) == (arm, "complete", 50.0, 4)
    store.purge(job.id)
    assert row(accounts, job.id) is None
    assert accounts.ratings()["count"] == 0


def test_new_assignment_resets_old_applied_model(client):  # noqa: F811
    store, accounts = client.app_state.store, client.app_state.accounts
    job = store.create("switch", "", ["guitar"])
    manifest(store, job.id, "fusion_rbf_svm", result={
        "method": "alpha_three_arm", "assigned_arm": "fusion_rbf_svm",
        "experiment_eligible": True, "assignment_probability": 1 / 3,
        "model_sha256": "b" * 64, "count": 2})
    store.update(job, state="running", started_at=1000.0)
    assert row(accounts, job.id)["applied_model"] == "fusion_rbf_svm"
    run = store.run_dir(job.id)
    data = json.loads((run / "manifest.json").read_text())
    data["config"]["guitar_count_arm"] = "fusion_extra_trees"
    data.pop("guitar_count")
    (run / "manifest.json").write_text(json.dumps(data))
    store.update(job, state="failed", finished_at=1010.0)
    saved = row(accounts, job.id)
    assert saved["assigned_model"] == "fusion_extra_trees"
    assert saved["applied_model"] is None
    assert saved["predicted_guitars"] is None


def test_restart_backfills_jobs_created_before_the_ledger_was_attached(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = store.create("older", "", ["guitar"])
    manifest(store, job.id, "fusion_stem_extra_trees")
    store.update(job, state="failed", started_at=100.0, finished_at=110.0)
    app = create_app(store, FakeRunner(), start_worker=False)
    saved = row(app.state.accounts, job.id)
    assert (saved["state"], saved["assigned_model"], saved["processing_seconds"]) == (
        "failed", "fusion_stem_extra_trees", 10.0)


def test_rejected_uploads_leave_no_experiment_row(tmp_path, monkeypatch):
    monkeypatch.setenv("ROCKY_MAX_UPLOAD_MB", "0")
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    app = create_app(store, FakeRunner(), start_worker=False)
    client = TestClient(app)
    for content, expected in ((b"audio", 413), (b"", 422)):
        response = client.post("/jobs", files={"file": ("song.wav", content, "audio/wav")},
                               data={"requested": "guitar"})
        assert response.status_code == expected
        assert store.all() == []
        assert app.state.accounts.db.execute("SELECT COUNT(*) FROM experiment_jobs").fetchone()[0] == 0


def test_restart_excludes_downtime_and_queue_wait(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = store.create("interrupted", "", ["guitar"])
    store.update(job, state="running", started_at=100.0)
    worker = Worker(store, FakeRunner())
    worker.threads = []  # inspect recovery without launching a background worker
    worker.start()
    recovered = store.get(job.id)
    assert recovered.state == "queued"
    assert recovered.started_at is None


def test_classifier_typo_fails_at_api_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("ROCKY_GUITAR_COUNT_CLASSIFIER", "extratrees")
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    with pytest.raises(ValueError, match="ROCKY_GUITAR_COUNT_CLASSIFIER"):
        create_app(store, FakeRunner(), start_worker=False)


def test_failed_experiment_delete_removes_files_and_keeps_the_worker_alive(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = store.create("gone", "", ["guitar"])
    audio = store.inputs / f"{job.id}.wav"
    audio.write_bytes(b"audio")
    store.run_dir(job.id).mkdir()
    store.update(job, filename=audio.name)

    def full_disk(_job_id):
        raise OSError("database or disk is full")

    store.on_purge = full_disk
    store.purge(job.id)
    assert not audio.exists() and not store.run_dir(job.id).exists()
    assert store.is_deleted(job.id) and store.get(job.id) is not None  # retried at next start

    store.on_purge = None
    worker = Worker(store, FakeRunner())
    worker.threads = []
    worker.start()
    assert store.get(job.id) is None and not store.is_deleted(job.id)


def test_worker_loop_survives_an_error_from_one_job(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    first, second = store.create("a", "", ["guitar"]), store.create("b", "", ["guitar"])
    store.update(first, state="queued")
    store.update(second, state="queued")
    worker = Worker(store, FakeRunner())
    seen = []

    class Stop(BaseException):
        pass

    def run(job):
        seen.append(job.id)
        store.update(job, state="failed")
        if len(seen) == 1:
            raise OSError("cleanup failed")
        raise Stop

    worker.run = run
    with pytest.raises(Stop):
        worker._loop()
    assert seen == [first.id, second.id]


@pytest.mark.parametrize("classifier", ["extra_trees", "rule"])
def test_rollback_model_is_not_recorded_when_it_did_not_run(tmp_path, classifier):
    run = tmp_path / "run"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"status": "complete", "config": {
        "guitar_count_classifier": classifier, "original": ["drums", "guitar"], "requested_guitars": 2}}))
    assert rating_model(run)["assigned_model"] is None
    (run / "manifest.json").write_text(json.dumps({"status": "complete", "config": {
        "guitar_count_classifier": classifier, "original": "unknown", "requested_guitars": 2}}))
    assert rating_model(run)["assigned_model"] == classifier
    if classifier == "rule":
        assert rating_model(run)["applied_model"] is None  # the guitar stage was not reached
        (run / "manifest.json").write_text(json.dumps({"status": "complete", "guitar_stereo": {}, "config": {
            "guitar_count_classifier": classifier, "original": "unknown", "requested_guitars": 2}}))
        assert rating_model(run)["applied_model"] == "rule"


def queued_job(store, title="song"):
    job = store.create(title, "", ["guitar"])
    store.update(job, state="queued")
    return job


def test_delete_reports_pending_until_rows_are_gone_and_worker_retries(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = store.create("gone", "", ["guitar"])
    store.update(job, state="failed")
    worker = Worker(store, FakeRunner())
    calls = []

    def flaky(job_id):
        calls.append(job_id)
        if len(calls) == 1:
            raise OSError("database or disk is full")

    store.on_purge = flaky
    assert worker.delete(job.id) == "pending"
    assert store.is_deleted(job.id)
    worker._settle_unfinished()
    assert store.get(job.id) is None and not store.is_deleted(job.id)
    assert store.pending_purges == set() and calls == [job.id, job.id]


def test_file_delete_error_still_removes_database_rows(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = store.create("gone", "", ["guitar"])
    audio = store.inputs / f"{job.id}.wav"
    audio.write_bytes(b"audio")
    rows = []
    store.on_purge = rows.append
    real_unlink = type(audio).unlink

    def denied(path, *args, **kwargs):
        if path == audio:
            raise PermissionError("denied")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(type(audio), "unlink", denied)
    assert store.purge(job.id) is False
    assert rows == [job.id] and store.is_deleted(job.id)
    monkeypatch.setattr(type(audio), "unlink", real_unlink)
    assert store.purge(job.id) is True
    assert not audio.exists() and store.get(job.id) is None


def test_hidden_deleted_job_does_not_take_a_queue_position(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    hidden, real = queued_job(store, "hidden"), queued_job(store, "real")
    store.tombstone(hidden.id).touch()
    assert Worker(store, FakeRunner()).queue_position(real.id) == 1


def test_stranded_running_job_gets_a_final_state_once_storage_recovers(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = store.create("stuck", "", ["guitar"])
    store.update(job, state="running", started_at=1.0)
    worker = Worker(store, FakeRunner())
    worker.stranded.add(job.id)
    real_update, failed = store.update, []

    def full_disk_once(*args, **kwargs):
        if not failed:
            failed.append(True)
            raise OSError("no space left on device")
        return real_update(*args, **kwargs)

    store.update = full_disk_once
    worker._settle_unfinished()
    assert store.get(job.id).state == "running" and worker.stranded == {job.id}
    worker._settle_unfinished()
    saved = store.get(job.id)
    assert saved.state == "failed" and saved.retryable and worker.stranded == set()


def test_worker_survives_a_claim_error(tmp_path):
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    job = queued_job(store)
    worker = Worker(store, FakeRunner())
    real_claim, seen = worker.claim, []

    class Stop(BaseException):
        pass

    def claim():
        if not seen:
            seen.append("error")
            raise OSError("no space left on device")
        return real_claim()

    def run(claimed):
        seen.append(claimed.id)
        raise Stop

    class NoWait:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def wait(self, timeout=None): pass

    worker.claim, worker.run, worker.cond = claim, run, NoWait()
    with pytest.raises(Stop):
        worker._loop()
    assert seen == ["error", job.id]


def test_startup_survives_an_experiment_record_error(tmp_path, monkeypatch):
    from rocky_server.accounts import Accounts
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    store.create("older", "", ["guitar"])

    def full_disk(*_args, **_kwargs):
        raise OSError("database or disk is full")

    monkeypatch.setattr(Accounts, "record_experiment_job", full_disk)
    assert create_app(store, FakeRunner(), start_worker=False) is not None
