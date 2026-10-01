"""Tests for POST /pipeline/match's async/background behavior and its
companion GET /pipeline/match/{run_id} status endpoint.

Fixes the same class of production bug test_pipeline_discover.py
already covers for /pipeline/discover: run_matching_for_user scores
every unseen job with a real, sequential Claude API call, and this
endpoint used to call it synchronously, inline. For most runs (a
tier's normal per-click cap) that stayed under the platform's request
timeout -- but NOT for a "welcome search" specifically
(settings.welcome_search_job_cap, deliberately deeper than either
tier's normal cap, for a brand-new account's very first search ever),
which is long enough to 502 before a synchronous response could ever
be sent. The browser reports that 502 as a CORS failure, since
Render's own timeout/error page doesn't carry the CORS headers a real
FastAPI response would have via its CORSMiddleware -- the CORS error
users saw was a symptom, not the real bug. "Preview as individual"
turned this from a rare, once-ever edge case into a routinely-hit one
by letting an admin account reach its own "first search ever" flow
repeatedly.

Deliberately does NOT exercise the real run_matching_for_user (that
hits the Claude API once per unseen job) -- monkeypatches it with a
fast, deterministic stand-in and focuses on what this fix actually
changed: immediate 202+run_id, the background task updating a
ScheduledRunLog row correctly on success/failure, that this new
interactive_match run_type is properly scoped away from other run
types sharing the same table, and that the pre-existing synchronous
validation (resume present, active profile present) still happens
before a background task is ever queued.

get_current_user is overridden via dependency_overrides, same pattern
as test_pipeline_discover.py and test_mentorship.py -- this is about
the async/polling behavior, not exercising the real auth system.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_user
from app import models
from app.services import pipeline_runner

client = TestClient(app)


_user_counter = [0]


def _make_user(db, email=None, resume_text="Experienced professional.", with_profile=True):
    _user_counter[0] += 1
    email = email or f"matchuser{_user_counter[0]}@x.com"
    user = models.User(email=email, hashed_password="x", resume_text=resume_text)
    db.add(user)
    db.commit()
    db.refresh(user)

    if with_profile:
        profile = models.SearchProfile(user_id=user.id, active=True, name="Default", titles='["Engineer"]')
        db.add(profile)
        db.commit()

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


_FAKE_RESULT = {
    "queued_application_ids": [1, 2],
    "usage_limit_reached": False,
    "near_misses": [],
    "hit_job_cap": False,
}


def test_match_returns_202_with_run_id(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    monkeypatch.setattr(pipeline_runner, "run_matching_for_user", lambda db, user, max_jobs=None, skip_usage_metering=False: _FAKE_RESULT)

    resp = client.post("/pipeline/match")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "started"
    assert isinstance(body["run_id"], int)


def test_match_background_task_marks_success(db, monkeypatch):
    """TestClient runs BackgroundTasks in-process before the request
    call returns, so the background task has already completed by the
    time we poll the status endpoint -- no sleep/retry loop needed
    here the way the real dashboard polling needs one against a
    slower, real backend."""
    user = _make_user(db)
    _login_as(user)

    monkeypatch.setattr(pipeline_runner, "run_matching_for_user", lambda db, user, max_jobs=None, skip_usage_metering=False: _FAKE_RESULT)

    start = client.post("/pipeline/match")
    run_id = start.json()["run_id"]

    status = client.get(f"/pipeline/match/{run_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "success"
    assert body["error"] is None
    assert body["result"]["queued_application_ids"] == [1, 2]
    assert body["result"]["usage_limit_reached"] is False
    assert body["result"]["hit_job_cap"] is False
    # Not this user's first-ever search (used_welcome_search defaults
    # to False, so this run itself IS the welcome search) -- confirms
    # the welcome-search cap-selection logic that moved into the
    # background function from the router still runs and tags its
    # output correctly.
    assert body["result"]["is_welcome_search"] is True


def test_match_background_task_marks_failed_on_exception(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    def boom(db, user, max_jobs=None, skip_usage_metering=False):
        raise RuntimeError("simulated Claude API outage")

    monkeypatch.setattr(pipeline_runner, "run_matching_for_user", boom)

    start = client.post("/pipeline/match")
    run_id = start.json()["run_id"]

    status = client.get(f"/pipeline/match/{run_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    assert "simulated Claude API outage" in body["error"]


def test_match_status_404_for_unknown_run_id(db):
    user = _make_user(db)
    _login_as(user)

    resp = client.get("/pipeline/match/999999")
    assert resp.status_code == 404


def test_match_status_scoped_away_from_discover_run_type(db):
    """A ScheduledRunLog row belonging to a different run_type
    (interactive_discover, scheduled_run, etc.) must not be readable
    through this match-specific status endpoint -- they share one
    table, but not one namespace of valid ids."""
    user = _make_user(db)
    _login_as(user)

    discover_log = models.ScheduledRunLog(run_type="interactive_discover", status="success")
    db.add(discover_log)
    db.commit()
    db.refresh(discover_log)

    resp = client.get(f"/pipeline/match/{discover_log.id}")
    assert resp.status_code == 404


def test_match_rejects_missing_resume_before_queuing_background_task(db, monkeypatch):
    """Validation that used to run inline before the (formerly
    synchronous) matching call must still run synchronously, before
    any background task is ever queued -- a 400 should come back
    immediately, with no ScheduledRunLog row created at all."""
    user = _make_user(db, resume_text="", with_profile=True)
    _login_as(user)

    call_count = [0]

    def fake_matching(db, user, max_jobs=None, skip_usage_metering=False):
        call_count[0] += 1
        return _FAKE_RESULT

    monkeypatch.setattr(pipeline_runner, "run_matching_for_user", fake_matching)

    resp = client.post("/pipeline/match")
    assert resp.status_code == 400
    assert call_count[0] == 0


def test_match_rejects_missing_active_profile_before_queuing_background_task(db, monkeypatch):
    user = _make_user(db, with_profile=False)
    _login_as(user)

    call_count = [0]

    def fake_matching(db, user, max_jobs=None, skip_usage_metering=False):
        call_count[0] += 1
        return _FAKE_RESULT

    monkeypatch.setattr(pipeline_runner, "run_matching_for_user", fake_matching)

    resp = client.post("/pipeline/match")
    assert resp.status_code == 400
    assert call_count[0] == 0


def test_match_marks_used_welcome_search_after_first_run(db, monkeypatch):
    """A user's very first successful match run must flip
    used_welcome_search so their next run takes the normal (not
    welcome) cap -- this is the flag that keeps the deep, slow welcome
    search a one-time-ever event rather than something repeatable."""
    user = _make_user(db)
    _login_as(user)
    assert user.used_welcome_search is False

    monkeypatch.setattr(pipeline_runner, "run_matching_for_user", lambda db, user, max_jobs=None, skip_usage_metering=False: _FAKE_RESULT)

    client.post("/pipeline/match")

    db.refresh(user)
    assert user.used_welcome_search is True
