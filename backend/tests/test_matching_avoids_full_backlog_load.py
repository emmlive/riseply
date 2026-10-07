"""Tests for the memory fix to run_matching_for_user's candidate
selection query.

Real production incident, confirmed via Render's own event log:
"Ran out of memory (used over 512MB) while running your code",
repeating several times a day. Root cause: the old query loaded the
ENTIRE shared unseen-job backlog as full ORM objects (including each
job's complete description text) just to sort/filter it down to a
`max_jobs` cap of 25-100 on an ordinary interactive "Find new
matches" click -- Greenhouse alone backs up to ~2,800 jobs per a
comment elsewhere in pipeline_runner.py, and the backlog only grows
over time as discovery keeps running, so the wasted memory on every
click got worse the longer the service stayed up.

The fix selects candidate job ids using a lightweight (id, title)
query first, THEN fetches full Job rows only for the ids actually
selected. These tests aren't able to directly assert on memory usage
from a test process, so they instead lock in behavioral correctness
of the two-step approach -- including the one new edge case it
introduces (a job disappearing between the lightweight selection
query and the full-row fetch) that didn't exist in the single-query
version.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import json
import pytest

import app.main  # noqa: F401 -- triggers table creation, see test_matching_candidate_priority.py

from app.database import SessionLocal
from app import models
from app.services import pipeline_runner

_user_counter = [0]


@pytest.fixture()
def db():
    session = SessionLocal()
    session.query(models.Job).delete()
    session.query(models.ScoredJob).delete()
    session.commit()
    yield session
    session.close()


def _make_user(db):
    _user_counter[0] += 1
    user = models.User(
        email=f"memfix{_user_counter[0]}@x.com", hashed_password="x",
        resume_text="Experienced security engineer, 5 years.",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_profile(db, user_id):
    profile = models.SearchProfile(
        user_id=user_id, name="Security roles",
        titles=json.dumps(["Security Engineer"]), locations=json.dumps([]), seniority=json.dumps([]),
        min_match_score=60, exclude_companies=json.dumps([]),
        keywords_required=json.dumps([]), keywords_excluded=json.dumps([]),
        active=True,
    )
    db.add(profile)
    db.commit()
    return profile


def _make_job(db, title, discovered_at, description="A job."):
    job = models.Job(
        source="test", external_id=uuid.uuid4().hex, company="Acme", title=title,
        location="Remote", description=description, discovered_at=discovered_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_capped_run_still_scores_full_job_data_not_just_title(db):
    """The two-step fetch must still hand the real description/
    location/salary fields to the scorer -- not just the lightweight
    id/title used for selection. Confirms the rebuild into full Job
    objects actually happened, not that it was silently skipped."""
    user = _make_user(db)
    _make_profile(db, user.id)

    now = datetime.utcnow()
    _make_job(db, "Security Engineer", now, description="Full posting text about security engineering.")

    seen_descriptions = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        seen_descriptions.append(job["description"])
        return {"profile_name": "Security roles", "score": 40, "reason": "meh", "meets_threshold": False}

    with patch.object(pipeline_runner.matcher, "best_profile_match", side_effect=fake_best_match):
        pipeline_runner.run_matching_for_user(db, user, max_jobs=5)

    assert seen_descriptions == ["Full posting text about security engineering."]


def test_job_deleted_between_selection_and_fetch_is_silently_skipped(db, monkeypatch):
    """The lightweight selection query and the full-row fetch are two
    separate queries now, not one atomic one -- a job could in theory
    be deleted (or otherwise vanish) in between. The old single-query
    version had no such gap. Must not KeyError; the vanished job is
    just silently excluded rather than crashing the whole run."""
    user = _make_user(db)
    _make_profile(db, user.id)

    now = datetime.utcnow()
    surviving = _make_job(db, "Security Engineer", now)
    vanishing = _make_job(db, "Senior Security Engineer", now - timedelta(hours=1))

    real_query = db.query

    def query_then_delete_vanishing(*args, **kwargs):
        q = real_query(*args, **kwargs)
        if args and args[0] is models.Job:
            # Simulate the race: by the time the full-row fetch runs,
            # `vanishing` has been removed (e.g. deleted by an admin,
            # or some other concurrent process) even though it was
            # still present for the earlier lightweight query.
            real_query(models.Job).filter(models.Job.id == vanishing.id).delete()
            db.commit()
        return q

    scored_titles = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        scored_titles.append(job["title"])
        return {"profile_name": "Security roles", "score": 40, "reason": "meh", "meets_threshold": False}

    with patch.object(pipeline_runner.matcher, "best_profile_match", side_effect=fake_best_match):
        with patch.object(db, "query", side_effect=query_then_delete_vanishing):
            result = pipeline_runner.run_matching_for_user(db, user, max_jobs=5)

    assert result["skipped_reason"] is None
    assert scored_titles == ["Security Engineer"]  # the vanished job never reached the scorer


def test_uncapped_run_still_loads_every_unseen_job(db):
    """max_jobs=None (the nightly scheduled batch) must still work
    through the ENTIRE unseen backlog -- the two-step query change is
    about avoiding over-fetching for the CAPPED case, not about
    silently shrinking the uncapped one."""
    user = _make_user(db)
    _make_profile(db, user.id)

    now = datetime.utcnow()
    for i in range(8):
        _make_job(db, f"Security Engineer {i}", now - timedelta(hours=i))

    scored_titles = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        scored_titles.append(job["title"])
        return {"profile_name": "Security roles", "score": 40, "reason": "meh", "meets_threshold": False}

    with patch.object(pipeline_runner.matcher, "best_profile_match", side_effect=fake_best_match):
        result = pipeline_runner.run_matching_for_user(db, user, max_jobs=None)

    assert len(scored_titles) == 8
    assert result["hit_job_cap"] is False
