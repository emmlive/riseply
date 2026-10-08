"""Progress: computed from existing rows, scoped to the signed-in user."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import progress as pg


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _user(db, **kw):
    u = models.User(email=f"pg{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", **kw)
    db.add(u)
    db.commit()
    return u


def _session(db, uid, score, days_ago, role="IT Auditor", topic="Controls", status="completed", stype="drill"):
    when = datetime.utcnow() - timedelta(days=days_ago)
    s = models.CareerCoachSession(
        user_id=uid, session_type=stype, target_role=role, topic=topic, status=status,
        score=score, created_at=when, completed_at=when if status == "completed" else None)
    db.add(s)
    db.commit()
    return s


def _job(db):
    j = models.Job(source="test", external_id=uuid.uuid4().hex, title="Auditor", company="Acme", url=f"https://x.test/{uuid.uuid4().hex}")
    db.add(j)
    db.commit()
    return j


def _app(db, uid, status, days_ago=1, submitted=False):
    j = _job(db)
    when = datetime.utcnow() - timedelta(days=days_ago)
    a = models.Application(user_id=uid, job_id=j.id, status=status, created_at=when,
                           submitted_at=when if submitted else None)
    db.add(a)
    db.commit()
    return a


def test_recent_change_needs_two_scores_and_compares_like_with_like():
    assert pg.recent_change([]) is None
    assert pg.recent_change([70]) is None
    assert pg.recent_change([60, 75]) == 15
    assert pg.recent_change([50, 60, 80]) == 20            # latest vs the one before
    assert pg.recent_change([50, 60, 70, 80, 90, 100]) == 30   # last 3 (90) vs the 3 before (60)
    assert pg.recent_change([80, 60]) == -20


def test_practice_summary():
    db = SessionLocal()
    u = _user(db)
    _session(db, u.id, 60, 10)
    _session(db, u.id, 70, 5, topic="Risk")
    _session(db, u.id, 85, 1)
    _session(db, u.id, None, 0, status="in_progress")
    _session(db, u.id, None, 2)    # completed without a score
    out = pg.build_progress(db, u)["practice"]
    assert out["sessions_completed"] == 4
    assert out["sessions_in_progress"] == 1
    assert out["scored_sessions"] == 3
    assert out["avg_score"] == pytest.approx(71.7, abs=0.1)
    assert out["best_score"] == 85 and out["latest_score"] == 85
    assert out["change"] == 15
    assert [p["score"] for p in out["scores"]] == [60, 70, 85]       # oldest first
    role = out["by_role"][0]
    assert role["target_role"] == "IT Auditor" and role["sessions"] == 4
    assert role["first_score"] == 60 and role["latest_score"] == 85 and role["change"] == 25
    assert [t["topic"] for t in out["weakest_topics"]] == ["Risk", "Controls"]    # 70 vs 72.5 average
    db.close()


def test_roles_are_grouped_case_insensitively():
    db = SessionLocal()
    u = _user(db)
    _session(db, u.id, 60, 3, role="Security Architect")
    _session(db, u.id, 70, 1, role="security architect ")
    roles = pg.build_progress(db, u)["practice"]["by_role"]
    assert len(roles) == 1 and roles[0]["sessions"] == 2
    db.close()


def test_funnel_and_rates():
    db = SessionLocal()
    u = _user(db)
    for status, sub in [("pending_approval", False), ("rejected", False), ("approved", False),
                        ("submitted", True), ("submitted", True), ("interviewing", True),
                        ("offer", True), ("closed", True)]:
        _app(db, u.id, status, submitted=sub)
    js = pg.build_progress(db, u)["job_search"]
    f = js["funnel"]
    # applied = submitted x2 + interviewing + offer + the closed one that had been submitted
    assert f == {"matched": 8, "approved": 6, "applied": 5, "interviewing": 2, "offers": 1}
    assert js["interview_rate"] == 40
    db.close()


def test_interview_rate_hidden_until_enough_applications():
    db = SessionLocal()
    u = _user(db)
    _app(db, u.id, "interviewing", submitted=True)
    assert pg.build_progress(db, u)["job_search"]["interview_rate"] is None
    db.close()


def test_weeks_cover_eight_weeks_oldest_first_and_count_activity():
    db = SessionLocal()
    u = _user(db)
    _app(db, u.id, "submitted", days_ago=1, submitted=True)
    _app(db, u.id, "approved", days_ago=40)
    _session(db, u.id, 70, 1)
    weeks = pg.build_progress(db, u)["job_search"]["weeks"]
    assert len(weeks) == 8
    assert [w["week_start"] for w in weeks] == sorted(w["week_start"] for w in weeks)
    assert all(w["week_start"].weekday() == 0 for w in weeks)
    assert sum(w["applied"] for w in weeks) == 1
    assert sum(w["matches"] for w in weeks) == 2
    assert sum(w["practice"] for w in weeks) == 1
    db.close()


def test_week_boundaries_follow_the_persons_timezone():
    db = SessionLocal()
    u = _user(db)
    # Monday 2026-10-05 02:00 UTC is still Sunday evening in Chicago (UTC-5).
    now = datetime(2026, 10, 8, 12, 0)
    when = datetime(2026, 10, 5, 2, 0)
    j = _job(db)
    db.add(models.Application(user_id=u.id, job_id=j.id, status="submitted", created_at=when, submitted_at=when))
    db.commit()
    utc = pg.build_progress(db, u, tz_offset=0, now=now)["job_search"]["weeks"][-1]
    chi = pg.build_progress(db, u, tz_offset=300, now=now)["job_search"]["weeks"][-1]
    assert utc["applied"] == 1      # this week (Monday in UTC)
    assert chi["applied"] == 0      # last week (Sunday in Chicago)
    db.close()


def test_endpoint_is_scoped_to_the_signed_in_user():
    db = SessionLocal()
    me, other = _user(db, rise_points=40, current_streak=3, longest_streak=9), _user(db)
    _session(db, me.id, 80, 1)
    _session(db, other.id, 10, 1)
    _app(db, other.id, "offer", submitted=True)
    mid = me.id
    db.close()

    from app.database import get_db
    from fastapi import Depends

    def _u(db=Depends(get_db)):
        return db.get(models.User, mid)
    app.dependency_overrides[get_current_user] = _u
    r = TestClient(app).get("/progress?tz_offset=300")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["practice"]["sessions_completed"] == 1 and body["practice"]["best_score"] == 80
    assert body["job_search"]["funnel"]["matched"] == 0
    assert body["current_streak"] == 3 and body["longest_streak"] == 9 and body["rise_points"] == 40
    assert TestClient(app).get("/progress?tz_offset=99999").status_code == 422


def test_empty_account_returns_zeros_not_errors():
    db = SessionLocal()
    u = _user(db)
    out = pg.build_progress(db, u)
    assert out["practice"]["sessions_completed"] == 0 and out["practice"]["avg_score"] is None
    assert out["practice"]["scores"] == [] and out["practice"]["change"] is None
    assert out["job_search"]["funnel"]["matched"] == 0 and len(out["job_search"]["weeks"]) == 8
    db.close()
