import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal, get_db
from app.main import app
from app.security import get_current_user
from app.services import job_alerts, pipeline_runner


def U(**kw):
    base = dict(alert_digest_hour=8, alert_timezone="America/Chicago", alert_instant_min_score=85,
                notification_min_score=0, last_digest_sent_at=None)
    base.update(kw)
    return NS(**base)


def test_digest_is_due_only_in_the_chosen_local_hour_and_once_a_day():
    # 14:00 UTC on Nov 11 is 8:00 in Chicago (CST).
    at = datetime(2026, 11, 11, 14, 5)
    assert job_alerts.is_due(U(), at)
    assert not job_alerts.is_due(U(), datetime(2026, 11, 11, 15, 5)), "wrong hour"
    assert not job_alerts.is_due(U(last_digest_sent_at=at - timedelta(hours=3)), at), "already sent today"
    assert job_alerts.is_due(U(alert_timezone="America/Los_Angeles", alert_digest_hour=6), at)


def test_unknown_timezone_is_rejected_and_falls_back_safely():
    assert not job_alerts.valid_timezone("Mars/Olympus")
    assert job_alerts.local_hour(U(alert_timezone="Mars/Olympus"), datetime(2026, 11, 11, 14, 0)) == 8


def test_only_standout_matches_are_instant_and_only_a_few_a_day():
    assert job_alerts.is_instant(90, U(), 0)
    assert not job_alerts.is_instant(80, U(), 0)
    assert not job_alerts.is_instant(95, U(), 3), "a fourth in a day waits for the digest"
    assert not job_alerts.is_instant(90, U(notification_min_score=95), 0), "the person's own floor still wins"


def _m(title, score, **kw):
    return {"title": title, "company": "Acme", "location": "Remote", "match_score": score, "match_reason": "Good overlap.",
            "url": "https://x/y", **kw}


def test_digest_ranks_best_first_caps_the_list_and_flags_stretch_roles():
    ms = [_m(f"Job {i}", 50 + i) for i in range(12)]
    ch = job_alerts.choose(ms, 85)
    assert ch["total"] == 12 and ch["extra"] == 4 and len(ch["good"]) == 8
    assert ch["good"][0]["match_score"] == 61
    text = job_alerts.digest_text(ch, datetime(2026, 11, 11))
    assert "Stretch role" in text and "4 more are waiting" in text


def test_html_escapes_job_text():
    ch = job_alerts.choose([_m("<script>x</script>", 90)], 85)
    h = job_alerts.digest_html(ch, datetime(2026, 11, 11))
    assert "<script>" not in h and "&lt;script&gt;" in h


def test_widen_suggestion_comes_from_the_search_itself():
    s = job_alerts.widen_suggestion([{"active": True, "min_match_score": 80, "locations": ["Chicago"], "titles": ["Auditor"]}])
    assert "65" in s and "Remote" in s and "titles" in s
    assert "no active search" in job_alerts.widen_suggestion([]).lower()
    assert job_alerts.widen_suggestion([{"active": True, "min_match_score": 60, "locations": ["Remote"], "titles": ["a", "b", "c"]}]) == ""


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"sa-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", full_name="Jane",
                       notification_preference="smart", alert_digest_hour=8, alert_timezone="America/Chicago",
                       alert_instant_min_score=85)
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    yield db, user, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def _app(db, user, title, score, alerted=None, when=None):
    j = models.Job(source="t", external_id=uuid.uuid4().hex, company="Acme", title=title, location="Remote", url="https://x")
    db.add(j); db.commit()
    a = models.Application(user_id=user.id, job_id=j.id, match_score=score, match_reason="why", alerted_at=alerted,
                           created_at=when or datetime(2026, 11, 11, 3, 0))
    db.add(a); db.commit()


def test_send_smart_alerts_sends_one_digest_without_repeating_instant_ones(ctx):
    db, user, _ = ctx
    user.last_digest_sent_at = datetime(2026, 11, 10, 14, 0)
    db.commit()
    _app(db, user, "Instant one", 92, alerted=datetime(2026, 11, 11, 3, 5))
    _app(db, user, "Waiting A", 70)
    _app(db, user, "Waiting B", 78)
    sent = []
    with patch("app.services.notifier.send_alert_digest", side_effect=lambda *a, **k: sent.append(a)):
        r = pipeline_runner.send_smart_alerts(db, datetime(2026, 11, 11, 14, 10))
    assert r["digests_sent"] == 1 and len(sent) == 1
    assert "Waiting B" in sent[0][2] and "Waiting A" in sent[0][2] and "Instant one" not in sent[0][2]
    db.refresh(user)
    assert user.last_digest_sent_at == datetime(2026, 11, 11, 14, 10)
    with patch("app.services.notifier.send_alert_digest") as again:
        pipeline_runner.send_smart_alerts(db, datetime(2026, 11, 11, 14, 40))
    assert not again.called, "never a second digest the same day"


def test_nothing_new_sends_nothing_at_first_then_one_quiet_note_after_a_week(ctx):
    db, user, _ = ctx
    with patch("app.services.notifier.send_email") as mail:
        pipeline_runner.send_smart_alerts(db, datetime(2026, 11, 11, 14, 10))
        assert not [c for c in mail.call_args_list if c[0][0] == user.email], "no email, and the clock starts"
        db.refresh(user)
        assert user.last_digest_sent_at is not None
        pipeline_runner.send_smart_alerts(db, datetime(2026, 11, 15, 14, 10))
        assert not [c for c in mail.call_args_list if c[0][0] == user.email], "four quiet days is not worth an email"
        pipeline_runner.send_smart_alerts(db, datetime(2026, 11, 19, 14, 10))
        mine = [c for c in mail.call_args_list if c[0][0] == user.email]
        assert len(mine) == 1 and "Nothing new" in mine[0][0][1]


def test_people_not_on_smart_are_left_alone(ctx):
    db, user, _ = ctx
    user.notification_preference = "every_match"; db.commit()
    _app(db, user, "X", 90)
    with patch("app.services.notifier.send_alert_digest") as s:
        pipeline_runner.send_smart_alerts(db, datetime(2026, 11, 11, 14, 10))
    assert not s.called


def test_settings_accept_smart_and_reject_a_bad_timezone(ctx):
    _, user, c = ctx
    ok = c.patch("/me", json={"notification_preference": "smart", "alert_digest_hour": 7, "alert_timezone": "America/New_York", "alert_instant_min_score": 90})
    assert ok.status_code == 200 and ok.json()["alert_digest_hour"] == 7 and ok.json()["alert_instant_min_score"] == 90
    bad = c.patch("/me", json={"alert_timezone": "Nowhere/Land"})
    assert bad.status_code == 400
    assert c.patch("/me", json={"alert_instant_min_score": 20}).status_code == 422


def test_preview_sends_a_sample_when_there_are_no_matches(ctx):
    _, _, c = ctx
    with patch("app.services.notifier.send_alert_digest") as s:
        r = c.post("/me/alerts/preview")
    assert r.status_code == 200 and r.json()["sample"] is True
    assert s.call_args[0][1].startswith("Preview:")
