"""Tests for the matching speed/cost changes in run_matching_for_user:
jobs are scored a few at a time (but results are still handled in the
original order), only the best N matches get an automatic resume
rewrite, and scoring failures are still refunded. Also covers the
stale-run cleanup in GET /pipeline/match/{run_id}.

matcher.best_profile_match and resume_customizer.customize_for_job are
mocked -- these tests are about orchestration, not model output.
"""
import json
import threading
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import pipeline_runner, usage

_n = [0]


@pytest.fixture()
def db():
    session = SessionLocal()
    session.query(models.Job).delete()
    session.query(models.ScoredJob).delete()
    session.commit()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _no_overrides():
    yield
    app.dependency_overrides.clear()


def _user(db):
    _n[0] += 1
    u = models.User(email=f"conc{_n[0]}@x.com", hashed_password="x", resume_text="Security engineer.")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(models.SearchProfile(
        user_id=u.id, name="P", titles=json.dumps(["Security"]), locations=json.dumps([]),
        seniority=json.dumps([]), min_match_score=60, exclude_companies=json.dumps([]),
        keywords_required=json.dumps([]), keywords_excluded=json.dumps([]), active=True,
    ))
    db.commit()
    return u


def _jobs(db, count):
    base = datetime.utcnow()
    out = []
    for i in range(count):
        j = models.Job(
            source="test", external_id=uuid.uuid4().hex, company=f"Co{i}", title=f"Security Engineer {i}",
            location="Remote", description="d", discovered_at=base - timedelta(minutes=i),
        )
        db.add(j)
        out.append(j)
    db.commit()
    return out


def _score_by_company(job, resume, profiles, ignore_location=False):
    # Co0 -> 90, Co1 -> 89, ... so the top matches are predictable.
    n = int(job["company"].replace("Co", ""))
    score = 90 - n
    return {"profile_name": "P", "score": score, "reason": "r", "meets_threshold": score >= 60}


def _fake_customize(user_id, resume_text, job, application_id):
    return f"r{application_id}.docx", b"docx", "why"


def test_only_top_n_matches_are_auto_tailored(db):
    user = _user(db)
    _jobs(db, 8)  # scores 90..83, all clear the bar
    tailored = []

    def fake_customize(user_id, resume_text, job, application_id):
        tailored.append(job["company"])
        return _fake_customize(user_id, resume_text, job, application_id)

    with patch("app.services.pipeline_runner.matcher.best_profile_match", side_effect=_score_by_company), \
         patch("app.services.pipeline_runner.resume_customizer.customize_for_job", side_effect=fake_customize), \
         patch("app.services.pipeline_runner.settings.auto_tailor_top_n", 3), \
         patch("app.services.pipeline_runner.notifier.notify_new_match"):
        result = pipeline_runner.run_matching_for_user(db, user, skip_usage_metering=True)

    assert len(result["queued_application_ids"]) == 8
    assert sorted(tailored) == ["Co0", "Co1", "Co2"]  # the three highest scores

    apps = db.query(models.Application).filter(models.Application.user_id == user.id).all()
    untailored = [a for a in apps if not a.tailored_resume_path]
    assert len(untailored) == 5
    assert all("Re-tailor" in (a.notes or "") for a in untailored)


def test_scoring_runs_concurrently_but_results_keep_order(db):
    user = _user(db)
    _jobs(db, 6)
    active = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def slow_score(job, resume, profiles, ignore_location=False):
        with lock:
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        threading.Event().wait(0.05)
        with lock:
            active["now"] -= 1
        return _score_by_company(job, resume, profiles)

    with patch("app.services.pipeline_runner.matcher.best_profile_match", side_effect=slow_score), \
         patch("app.services.pipeline_runner.resume_customizer.customize_for_job", side_effect=_fake_customize), \
         patch("app.services.pipeline_runner.settings.matching_concurrency", 4), \
         patch("app.services.pipeline_runner.settings.auto_tailor_top_n", 0), \
         patch("app.services.pipeline_runner.notifier.notify_new_match"):
        result = pipeline_runner.run_matching_for_user(db, user, skip_usage_metering=True)

    assert active["peak"] > 1  # actually ran in parallel
    ids = result["queued_application_ids"]
    scores = [db.get(models.Application, i).match_score for i in ids]
    assert scores == sorted(scores, reverse=True)  # processed in original (recency = score) order


def test_failed_scoring_is_refunded_and_skipped(db):
    user = _user(db)
    _jobs(db, 4)

    def flaky(job, resume, profiles, ignore_location=False):
        if job["company"] == "Co1":
            raise RuntimeError("model hiccup")
        return _score_by_company(job, resume, profiles)

    with patch("app.services.pipeline_runner.matcher.best_profile_match", side_effect=flaky), \
         patch("app.services.pipeline_runner.resume_customizer.customize_for_job", side_effect=_fake_customize), \
         patch("app.services.pipeline_runner.notifier.notify_new_match"):
        result = pipeline_runner.run_matching_for_user(db, user)  # metered

    assert len(result["queued_application_ids"]) == 3
    assert usage.get_usage(db, user.id, "match") == 3  # 4 charged, 1 refunded


def test_stale_running_match_is_reported_failed(db):
    user = _user(db)
    old = models.ScheduledRunLog(
        run_type="interactive_match", status="running",
        started_at=datetime.utcnow() - timedelta(minutes=50),
    )
    fresh = models.ScheduledRunLog(
        run_type="interactive_match", status="running",
        started_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add_all([old, fresh])
    db.commit()
    old_id, fresh_id = old.id, fresh.id

    def _login(session_db=None):
        from app.database import get_db
        from fastapi import Depends

        def _u(db=Depends(get_db)):
            return db.get(models.User, user.id)
        return _u

    app.dependency_overrides[get_current_user] = _login()
    client = TestClient(app)

    stale = client.get(f"/pipeline/match/{old_id}").json()
    assert stale["status"] == "failed"
    assert "interrupted" in stale["error"]

    assert client.get(f"/pipeline/match/{fresh_id}").json()["status"] == "running"
