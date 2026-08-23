"""Tests for POST /internal/scheduled-run's async/background behavior
and its companion GET /internal/scheduled-run/{run_id} status endpoint.

Deliberately does NOT exercise the real discovery+matching pipeline
(that hits Greenhouse, Lever, RSS feeds, RemoteOK, Arbeitnow, and
potentially the live Claude API) -- these tests monkeypatch
pipeline_runner.run_scheduled_matching_batch with a fast, deterministic
stand-in and focus on what this PR actually changed: that the endpoint
returns immediately with a run_id, that the background task updates a
ScheduledRunLog row correctly on both success and failure, and that the
existing secret-gating behavior (503 when unconfigured, 401 on a wrong
secret) is unchanged.

DATABASE_URL and CRON_SECRET are set at MODULE level, before app.main
(and everything it imports) is ever imported -- app.config's `settings`
singleton and app.database's `engine` are both built once at import
time from these env vars, so setting them per-test via monkeypatch
would be too late: the already-cached modules wouldn't see the change.
For the "secret unconfigured" case, settings.cron_secret is
monkeypatched directly on the live singleton instead of via env var.
"""
import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="riseply_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ["CRON_SECRET"] = "test-secret-value"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services import pipeline_runner

HEADERS = {"X-Cron-Secret": "test-secret-value"}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_scheduled_run_503_when_secret_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    resp = client.post("/internal/scheduled-run", headers=HEADERS)
    assert resp.status_code == 503


def test_scheduled_run_401_on_wrong_secret(client):
    resp = client.post("/internal/scheduled-run", headers={"X-Cron-Secret": "wrong"})
    assert resp.status_code == 401


def test_scheduled_run_returns_202_with_run_id(client, monkeypatch):
    monkeypatch.setattr(
        pipeline_runner, "run_scheduled_matching_batch",
        lambda db: {"discovery": {}, "users_processed": 0, "results": {}},
    )

    resp = client.post("/internal/scheduled-run", headers=HEADERS)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "started"
    assert isinstance(body["run_id"], int)


def test_scheduled_run_background_task_marks_success(client, monkeypatch):
    """TestClient runs BackgroundTasks in-process before the request
    call returns, so by the time we poll the status endpoint the
    background task has already completed -- no sleep/retry loop
    needed here the way the real GitHub Actions workflow needs one
    against a real, slower backend."""
    fake_result = {"discovery": {"jobs_added": 3}, "users_processed": 2, "results": {"a@x.com": {"queued": 1}}}
    monkeypatch.setattr(
        pipeline_runner, "run_scheduled_matching_batch",
        lambda db: fake_result,
    )

    start_resp = client.post("/internal/scheduled-run", headers=HEADERS)
    run_id = start_resp.json()["run_id"]

    status_resp = client.get(f"/internal/scheduled-run/{run_id}", headers=HEADERS)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "success"
    assert body["result"] == fake_result
    assert body["error"] is None
    assert body["finished_at"] is not None


def test_scheduled_run_background_task_marks_failed_on_exception(client, monkeypatch):
    def boom(db):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(pipeline_runner, "run_scheduled_matching_batch", boom)

    start_resp = client.post("/internal/scheduled-run", headers=HEADERS)
    run_id = start_resp.json()["run_id"]

    status_resp = client.get(f"/internal/scheduled-run/{run_id}", headers=HEADERS)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "failed"
    assert "simulated pipeline failure" in body["error"]


def test_scheduled_run_status_404_for_unknown_id(client):
    resp = client.get("/internal/scheduled-run/999999", headers=HEADERS)
    assert resp.status_code == 404


def test_scheduled_run_status_requires_secret(client):
    resp = client.get("/internal/scheduled-run/1", headers={"X-Cron-Secret": "wrong"})
    assert resp.status_code == 401
