"""Alpha denominators include unrated and failed jobs, but honor song deletion."""

import json
from fastapi.testclient import TestClient

from rocky_server.app import create_app
from rocky_server.jobs import JobStore, Worker
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
    import pytest
    monkeypatch.setenv("ROCKY_GUITAR_COUNT_CLASSIFIER", "extratrees")
    store = JobStore(tmp_path / "app", tmp_path / "runs", tmp_path / "input")
    with pytest.raises(ValueError, match="ROCKY_GUITAR_COUNT_CLASSIFIER"):
        create_app(store, FakeRunner(), start_worker=False)
