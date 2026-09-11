"""Test for the fix to the recurring "Daily job matching: All jobs have
failed" GitHub Actions failures -- the scheduled batch job used to
score an uncapped number of unseen jobs per user, sequentially, inside
the same process that also has to answer the external scheduler's
status-check polling. As the user base and job pool grew, total
runtime grew past what the server could sustain while still responding
to anything else, which the scheduler's poller saw as sustained HTTP
502s rather than a slow-but-eventually-successful run.

Mocks run_discovery and run_matching_for_user rather than exercising
the real pipeline (which hits external job boards and the live Claude
API) -- focuses purely on confirming run_scheduled_matching_batch
actually passes the new cap through, which is the specific behavior
this fix changed.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.config import settings
from app.services import pipeline_runner
from app import models


@pytest.fixture()
def db():
    # Importing app.main alone doesn't create tables -- that happens
    # via a FastAPI startup event, which only actually runs inside a
    # TestClient context manager (matching test_internal_scheduled_run.
    # py's own setup). A plain SessionLocal() without this would hit
    # "no such table" on a fresh test database.
    with TestClient(app):
        session = SessionLocal()
        yield session
        session.close()


def _make_user_with_active_profile(db, email):
    user = models.User(email=email, hashed_password="x", full_name="Test User", resume_text="Experienced professional.")
    db.add(user)
    db.commit()
    db.refresh(user)
    profile = models.SearchProfile(user_id=user.id, active=True, name="Default", titles='["Engineer"]')
    db.add(profile)
    db.commit()
    return user


def test_scheduled_batch_passes_the_configured_cap_to_matching(db):
    user = _make_user_with_active_profile(db, "scheduledcap1@x.com")

    with patch.object(pipeline_runner, "run_discovery", return_value={"jobs_added": 0}), \
         patch.object(pipeline_runner, "run_matching_for_user") as mock_match:
        mock_match.return_value = {"queued_application_ids": [], "usage_limit_reached": False}
        pipeline_runner.run_scheduled_matching_batch(db)

    # Checks the call made FOR THIS SPECIFIC USER, not that the mock was
    # called exactly once overall -- the batch queries every qualifying
    # user in the database, and this suite shares one database across
    # the whole test run (see conftest.py), so other qualifying users
    # from other test files may also trigger a call.
    matching_calls = [c for c in mock_match.call_args_list if c.args[1].id == user.id]
    assert len(matching_calls) == 1
    assert matching_calls[0].kwargs["max_jobs"] == settings.scheduled_run_max_jobs_per_user


def test_scheduled_batch_cap_is_a_bounded_positive_number(db):
    """A basic sanity guard against this ever silently regressing back
    to an effectively-uncapped value (None, zero, or absurdly large) --
    the whole point of the fix is a genuinely bounded per-run cost."""
    assert isinstance(settings.scheduled_run_max_jobs_per_user, int)
    assert 0 < settings.scheduled_run_max_jobs_per_user <= 100


def test_scheduled_batch_skips_users_without_active_profile(db):
    """Confirms the cap change didn't disturb the existing
    skip-inactive-users logic alongside it. Checks that THIS specific
    user is never passed to run_matching_for_user, rather than
    asserting the mock is never called at all -- the batch queries
    every qualifying user in the database, and this suite shares one
    database across the whole test run (see conftest.py), so a
    same-file test that ran first may have already left behind a
    real qualifying user of its own."""
    user = models.User(email="scheduledcap2@x.com", hashed_password="x", full_name="No Profile", resume_text="Resume text.")
    db.add(user)
    db.commit()

    with patch.object(pipeline_runner, "run_discovery", return_value={"jobs_added": 0}), \
         patch.object(pipeline_runner, "run_matching_for_user") as mock_match:
        pipeline_runner.run_scheduled_matching_batch(db)

    called_user_ids = {call.args[1].id for call in mock_match.call_args_list}
    assert user.id not in called_user_ids
