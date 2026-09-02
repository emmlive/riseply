"""Tests for the keyword-priority reordering added to
run_matching_for_user's candidate selection when max_jobs caps the
batch (the interactive "Find new matches" button, tier-limited).

Root cause this fixes: candidate jobs were selected purely by recency
across the ENTIRE shared, cross-industry job pool, with no title/
keyword pre-filter. A capped search's whole budget could go to
completely unrelated postings just because they were the most
recently discovered ones in the pool, even when older, genuinely
relevant postings existed further back -- explaining a real user
report of "search results don't relate to my profile."

matcher.best_profile_match is mocked throughout -- these tests are
about WHICH jobs get selected for scoring and in what order, not
about the LLM's actual judgment of any one job.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import json
import pytest

# Triggers table creation as an import side effect (run_migration() at
# module level in app.main) -- other test files get this for free via
# importing `from app.main import app` for the TestClient; this file
# doesn't need the app/TestClient itself, just the DB schema to exist.
import app.main  # noqa: F401

from app.database import SessionLocal
from app import models
from app.services import pipeline_runner, matcher

_user_counter = [0]


@pytest.fixture()
def db():
    session = SessionLocal()
    # models.Job is explicitly a GLOBAL table, shared across all users
    # by design (see its own docstring) -- not scoped to a tenant/user
    # the way almost everything else in this codebase is. That's
    # correct for production, but it means these tests, sharing one
    # SQLite file for the whole module (same DATABASE_URL-at-import-
    # time reasoning as other test files in this project), would
    # otherwise leak jobs between tests: a fresh user in test #2 has
    # never scored test #1's leftover Job rows, so they'd show up as
    # "unseen" and inflate/pollute the candidate pool test #2 is
    # actually trying to construct. Clearing it at the start of every
    # test keeps each one's job pool exactly what it creates, matching
    # what the assertions actually expect.
    session.query(models.Job).delete()
    session.query(models.ScoredJob).delete()
    session.commit()
    yield session
    session.close()


def _make_user(db, email=None):
    # Auto-incrementing per call rather than one shared default string
    # -- every test in this file called _make_user(db) with no
    # argument, so a shared default collided against User.email's
    # unique constraint the moment a second test tried to insert its
    # own "candidate@x.com" into the same (session-shared) database.
    _user_counter[0] += 1
    email = email or f"candidate{_user_counter[0]}@x.com"
    user = models.User(email=email, hashed_password="x", resume_text="Experienced security engineer, 5 years.")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_profile(db, user_id, titles, keywords_required=None):
    profile = models.SearchProfile(
        user_id=user_id, name="Security roles",
        titles=json.dumps(titles), locations=json.dumps([]), seniority=json.dumps([]),
        min_match_score=60, exclude_companies=json.dumps([]),
        keywords_required=json.dumps(keywords_required or []), keywords_excluded=json.dumps([]),
        active=True,
    )
    db.add(profile)
    db.commit()
    return profile


def _make_job(db, title, discovered_at):
    # uuid4 rather than an incrementing counter -- Job's uniqueness
    # constraint is on (source, external_id) globally across the whole
    # shared test database (every test file's tests share one SQLite
    # file), and a simple per-file counter starting at 1 is guaranteed
    # to eventually collide with any OTHER file's own independently-
    # starting counter using the same source="test" string (this
    # exact collision happened against test_mentorship.py's own
    # _job_counter). A random UUID has no such collision risk against
    # any other file, present or future, without every test file
    # needing to coordinate on non-overlapping numeric ranges.
    job = models.Job(
        source="test", external_id=uuid.uuid4().hex, company="Acme", title=title,
        location="Remote", description="A job.", discovered_at=discovered_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_relevant_older_jobs_prioritized_over_irrelevant_newer_ones_when_capped(db):
    """The exact bug scenario: 3 irrelevant jobs discovered MORE
    recently than 2 relevant ones. With max_jobs=2 (tighter than the
    5 total unseen jobs), the two Security Engineer postings should
    still be the ones scored, despite being older.

    The two relevant jobs are scored as real matches (meets_threshold)
    so they get queued -- this matters for test isolation, not just
    realism: run_matching_for_user's location-fallback pass only fires
    when NOTHING got queued this run, and it would otherwise score
    additional jobs beyond the capped primary pass, contaminating what
    this test is actually checking (which jobs the PRIMARY,
    keyword-prioritized selection picked)."""
    user = _make_user(db)
    _make_profile(db, user.id, titles=["Security Engineer"])

    now = datetime.utcnow()
    # Older, relevant
    _make_job(db, "Security Engineer", now - timedelta(hours=5))
    _make_job(db, "Senior Security Engineer", now - timedelta(hours=4))
    # Newer, irrelevant
    _make_job(db, "Marketing Coordinator", now - timedelta(hours=3))
    _make_job(db, "Warehouse Associate", now - timedelta(hours=2))
    _make_job(db, "Retail Store Manager", now - timedelta(hours=1))

    scored_titles = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        scored_titles.append(job["title"])
        is_relevant = "security engineer" in job["title"].lower()
        return {
            "profile_name": "Security roles" if is_relevant else None,
            "score": 85 if is_relevant else 20,
            "reason": "good fit" if is_relevant else "not a great fit",
            "meets_threshold": is_relevant,
        }

    with patch.object(matcher, "best_profile_match", side_effect=fake_best_match):
        pipeline_runner.run_matching_for_user(db, user, max_jobs=2)

    assert set(scored_titles) == {"Security Engineer", "Senior Security Engineer"}


def test_falls_back_to_recency_when_not_enough_relevant_jobs_to_fill_cap(db):
    """Only 1 relevant job exists; cap is 3. The relevant one should
    still be included, with recency filling the remaining 2 slots.
    The relevant job queues (meets_threshold=True) so the location-
    fallback pass doesn't fire and contaminate scored_titles with
    jobs beyond this test's capped primary-pass selection."""
    user = _make_user(db)
    _make_profile(db, user.id, titles=["Security Engineer"])

    now = datetime.utcnow()
    _make_job(db, "Security Engineer", now - timedelta(hours=10))  # relevant, oldest
    _make_job(db, "Marketing Coordinator", now - timedelta(hours=3))
    _make_job(db, "Warehouse Associate", now - timedelta(hours=2))
    _make_job(db, "Retail Store Manager", now - timedelta(hours=1))  # most recent

    scored_titles = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        scored_titles.append(job["title"])
        is_relevant = "security engineer" in job["title"].lower()
        return {
            "profile_name": "Security roles" if is_relevant else None,
            "score": 85 if is_relevant else 20,
            "reason": "good fit" if is_relevant else "not a great fit",
            "meets_threshold": is_relevant,
        }

    with patch.object(matcher, "best_profile_match", side_effect=fake_best_match):
        pipeline_runner.run_matching_for_user(db, user, max_jobs=3)

    assert "Security Engineer" in scored_titles
    assert len(scored_titles) == 3
    # The 2 most recent irrelevant jobs fill the remaining slots, not the
    # least recent one -- recency ordering is preserved WITHIN each group.
    assert "Retail Store Manager" in scored_titles
    assert "Warehouse Associate" in scored_titles
    assert "Marketing Coordinator" not in scored_titles


def test_uncapped_run_scores_everything_regardless_of_relevance_ordering(db):
    """max_jobs=None (the nightly batch job) doesn't need reordering --
    it works through every unseen job regardless of order, so this
    just confirms the new logic doesn't accidentally engage or drop
    anything when there's no cap to begin with."""
    user = _make_user(db)
    _make_profile(db, user.id, titles=["Security Engineer"])

    now = datetime.utcnow()
    _make_job(db, "Security Engineer", now - timedelta(hours=2))
    _make_job(db, "Marketing Coordinator", now - timedelta(hours=1))

    scored_titles = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        scored_titles.append(job["title"])
        return {"profile_name": None, "score": 40, "reason": "not a great fit", "meets_threshold": False}

    with patch.object(matcher, "best_profile_match", side_effect=fake_best_match):
        pipeline_runner.run_matching_for_user(db, user, max_jobs=None)

    assert set(scored_titles) == {"Security Engineer", "Marketing Coordinator"}


def test_no_keyword_terms_falls_back_to_pure_recency(db):
    """A profile with no titles and no keywords_required has nothing
    to prioritize by -- should behave exactly as before (pure
    recency), not crash or exclude everything. "New Job" queues
    (meets_threshold=True) so the location-fallback pass doesn't fire
    and pull in "Old Job" too, which would otherwise contaminate this
    test's check of what the capped PRIMARY pass alone selected."""
    user = _make_user(db)
    _make_profile(db, user.id, titles=[], keywords_required=[])

    now = datetime.utcnow()
    _make_job(db, "Old Job", now - timedelta(hours=5))
    _make_job(db, "New Job", now - timedelta(hours=1))

    scored_titles = []

    def fake_best_match(job, resume_text, profiles, ignore_location=False):
        scored_titles.append(job["title"])
        is_new = job["title"] == "New Job"
        return {
            "profile_name": "x" if is_new else None,
            "score": 85 if is_new else 20,
            "reason": "fit", "meets_threshold": is_new,
        }

    with patch.object(matcher, "best_profile_match", side_effect=fake_best_match):
        pipeline_runner.run_matching_for_user(db, user, max_jobs=1)

    # Pure recency: the newest job should be the one scored.
    assert scored_titles == ["New Job"]
