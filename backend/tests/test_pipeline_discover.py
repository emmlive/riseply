"""Tests for POST /pipeline/discover's async/background behavior and
its companion GET /pipeline/discover/{run_id} status endpoint.

Fixes a real production bug: run_discovery makes dozens of sequential
external HTTP calls (Greenhouse per-company, Lever, RSS, RemoteOK,
Arbeitnow, Adzuna, USAJobs) and was previously called synchronously
from the "Find new matches" button, holding one request open long
enough to exceed the platform's timeout -- producing a 502 that the
browser reported as a CORS failure (Render's own timeout/error page
doesn't carry the CORS headers a real FastAPI response would have via
its CORSMiddleware, which is what a browser was actually reacting to).

Deliberately does NOT exercise the real run_discovery (that hits every
external job source) -- monkeypatches it with a fast, deterministic
stand-in and focuses on what this fix actually changed: immediate
202+run_id, the background task updating a ScheduledRunLog row
correctly on success/failure, and that this new interactive_discover
run_type is properly scoped away from the pre-existing scheduled_run
one sharing the same table.

get_current_user is overridden via dependency_overrides, same pattern
as test_mentorship.py -- this is about the async/polling behavior, not
exercising the real auth system.
"""
import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="riseply_discover_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_user
from app import models
from app.services import pipeline_runner

client = TestClient(app)


_user_counter = [0]


def _make_user(db, email=None):
    _user_counter[0] += 1
    email = email or f"discoveruser{_user_counter[0]}@x.com"
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def db():
    from app.database import SessionLocal
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _login_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_discover_returns_202_with_run_id(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    monkeypatch.setattr(pipeline_runner, "run_discovery", lambda db: {"jobs_added": 3})

    resp = client.post("/pipeline/discover")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "started"
    assert isinstance(body["run_id"], int)


def test_discover_background_task_marks_success(db, monkeypatch):
    """TestClient runs BackgroundTasks in-process before the request
    call returns, so the background task has already completed by the
    time we poll the status endpoint -- no sleep/retry loop needed
    here the way the real dashboard polling needs one against a
    slower, real backend."""
    user = _make_user(db)
    _login_as(user)

    fake_result = {"greenhouse": 5, "lever": 2, "rss": 1}
    monkeypatch.setattr(pipeline_runner, "run_discovery", lambda db: fake_result)

    start = client.post("/pipeline/discover")
    run_id = start.json()["run_id"]

    status = client.get(f"/pipeline/discover/{run_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "success"
    assert body["result"] == fake_result
    assert body["error"] is None


def test_discover_background_task_marks_failed_on_exception(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    def boom(db):
        raise RuntimeError("simulated source outage")

    monkeypatch.setattr(pipeline_runner, "run_discovery", boom)

    start = client.post("/pipeline/discover")
    run_id = start.json()["run_id"]

    status = client.get(f"/pipeline/discover/{run_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    assert "simulated source outage" in body["error"]


def test_discover_status_404_for_unknown_run_id(db):
    user = _make_user(db)
    _login_as(user)

    resp = client.get("/pipeline/discover/999999")
    assert resp.status_code == 404


def test_discover_status_scoped_away_from_scheduled_run_type(db):
    """A ScheduledRunLog row that belongs to the OTHER run_type
    (scheduled_run, used by /internal/scheduled-run) must not be
    readable through this interactive endpoint -- they share one
    table, but not one namespace of valid ids."""
    user = _make_user(db)
    _login_as(user)

    scheduled_log = models.ScheduledRunLog(run_type="scheduled_run", status="success")
    db.add(scheduled_log)
    db.commit()
    db.refresh(scheduled_log)

    resp = client.get(f"/pipeline/discover/{scheduled_log.id}")
    assert resp.status_code == 404
