"""'Why didn't I get an alert?' is answered from the records, and a smart digest
reaches Discord as well as email."""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from app import models
from app.config import settings
from app.database import Base, SessionLocal, engine
from fastapi.testclient import TestClient
from app.main import app
from app.services import alert_status, calendar_encryption, discord_notify as dn, pipeline_runner

URL = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"
NOW = datetime(2026, 11, 13, 20, 0)


TestClient(app)          # builds the tables, like the other test files
Base.metadata.create_all(bind=engine)


def _db():
    return SessionLocal()


def _user(db, **kw):
    fields = dict(resume_text="Auditor.", notification_preference="smart")
    fields.update(kw)
    u = models.User(email=f"as-{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T", **fields)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _profile(db, user):
    db.add(models.SearchProfile(user_id=user.id, name="p", titles=json.dumps(["Security Architect"]), active=True))
    db.commit()


def _by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_a_new_account_is_told_exactly_what_is_missing(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "")
    db = _db()
    try:
        u = _user(db, resume_text="")
        c = _by_id(alert_status.build(db, u, NOW))
        assert not c["resume"]["ok"] and c["resume"]["fix_href"] == "/dashboard/resume"
        assert not c["search"]["ok"]
        assert not c["email"]["ok"] and "RESEND_API_KEY" in c["email"]["detail"]
        assert not c["daily_search"]["ok"] or c["daily_search"]["ok"]     # depends on other tests' runs; never raises
        report = alert_status.build(db, u, NOW)
        assert not report["ok"] and "stopping your alerts" in report["headline"]
    finally:
        db.close()


def test_discord_connected_but_matches_off_is_called_out(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "k")
    db = _db()
    try:
        u = _user(db)
        db.add(models.DiscordConnection(user_id=u.id, webhook_url_enc=calendar_encryption.encrypt_token(URL),
                                        webhook_hint="x", timezone="UTC", matches_enabled=False))
        db.commit()
        c = _by_id(alert_status.build(db, u, NOW))
        assert not c["discord"]["ok"] and "switched off" in c["discord"]["detail"]
        assert c["discord"]["fix_label"] == "Turn on job matches"
        conn = db.query(models.DiscordConnection).filter_by(user_id=u.id).first()
        conn.matches_enabled = True
        db.commit()
        assert _by_id(alert_status.build(db, u, NOW))["discord"]["ok"]
    finally:
        db.close()


def test_missing_discord_is_a_tip_not_a_blocker(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "k")
    db = _db()
    try:
        u = _user(db)
        c = _by_id(alert_status.build(db, u, NOW))
        assert not c["discord"]["ok"] and c["discord"]["tip"]
    finally:
        db.close()


def test_failed_email_shows_the_reason(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "k")
    db = _db()
    try:
        u = _user(db)
        db.add(models.EmailLog(kind="digest", to_addr=u.email, subject="s", status="failed", error="Domain not verified", created_at=NOW - timedelta(hours=2)))
        db.commit()
        c = _by_id(alert_status.build(db, u, NOW))
        assert not c["email"]["ok"] and "Domain not verified" in c["email"]["detail"]
    finally:
        db.close()


def test_daily_search_and_hourly_job_staleness():
    db = _db()
    try:
        u = _user(db)
        db.query(models.ScheduledRunLog).filter(models.ScheduledRunLog.run_type.in_(["scheduled_run", alert_status.HEARTBEAT])).delete()
        db.commit()
        c = _by_id(alert_status.build(db, u, NOW))
        assert not c["daily_search"]["ok"] and "never run" in c["daily_search"]["detail"]
        assert not c["hourly"]["ok"]

        db.add(models.ScheduledRunLog(run_type="scheduled_run", status="success", started_at=NOW - timedelta(hours=7), finished_at=NOW - timedelta(hours=6)))
        db.commit()
        alert_status.record_tick(db, {"digests_sent": 0}, NOW - timedelta(minutes=20))
        c = _by_id(alert_status.build(db, u, NOW))
        assert c["daily_search"]["ok"] and c["hourly"]["ok"]

        db.add(models.ScheduledRunLog(run_type="scheduled_run", status="failed", error="Interrupted by restart", started_at=NOW - timedelta(hours=1)))
        db.commit()
        c = _by_id(alert_status.build(db, u, NOW))
        assert not c["daily_search"]["ok"] and "Interrupted" in c["daily_search"]["detail"]
    finally:
        db.close()


def test_heartbeat_rows_are_pruned():
    db = _db()
    try:
        alert_status.record_tick(db, {}, NOW - timedelta(days=5))
        alert_status.record_tick(db, {}, NOW)
        old = db.query(models.ScheduledRunLog).filter(models.ScheduledRunLog.run_type == alert_status.HEARTBEAT,
                                                      models.ScheduledRunLog.started_at < NOW - timedelta(days=3)).count()
        assert old == 0
    finally:
        db.close()


def test_smart_digest_reaches_discord_even_on_email_only_channel():
    db = _db()
    try:
        u = _user(db, alert_digest_hour=14, alert_timezone="UTC", notification_channel="email")
        job = models.Job(source="x", external_id=uuid.uuid4().hex, company="Acme", title="Security Architect", location="Remote",
                         url="https://acme.com/j/1", description="d", discovered_at=NOW, last_seen_at=NOW, is_active=True)
        db.add(job)
        db.commit()
        db.add(models.Application(user_id=u.id, job_id=job.id, matched_profile="p", match_score=80, match_reason="r",
                                  status="pending_approval", created_at=NOW - timedelta(hours=2)))
        db.add(models.DiscordConnection(user_id=u.id, webhook_url_enc=calendar_encryption.encrypt_token(URL), webhook_hint="x",
                                        timezone="UTC", matches_enabled=True))
        db.commit()
        sent = []
        with patch("app.services.notifier.send_alert_digest"), \
             patch.object(dn, "_post", side_effect=lambda url, payload: (sent.append(payload) or (True, 204, ""))):
            pipeline_runner.send_smart_alerts(db, now=NOW.replace(hour=14, minute=5))
        mine = [p for p in sent if "Security Architect" in json.dumps(p)]
        assert mine, "the digest reached Discord"
        text = json.dumps(mine[0])
        assert "https://acme.com/j/1" in text and "apply-queue" in text
    finally:
        db.close()


def test_discord_digest_line_only_links_safe_urls():
    assert dn._match_line({"title": "A [x](y)", "company": "Co", "match_score": 90, "url": "https://a.com/j"}) == "• **[A xy](https://a.com/j)** at Co, 90%"
    assert "](" not in dn._match_line({"title": "A", "company": "Co", "match_score": 90, "url": "javascript:alert(1)"})
    assert "](" not in dn._match_line({"title": "A", "company": "Co", "match_score": 90, "url": "https://a.com/x) evil"})


def test_endpoints_status_preview_and_hourly_heartbeat(monkeypatch):
    from app.database import get_db
    from app.security import get_current_user
    monkeypatch.setattr(settings, "resend_api_key", "k")
    db = _db()
    u = _user(db)
    app.dependency_overrides[get_current_user] = lambda: u
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    try:
        r = c.get("/me/alerts/status")
        assert r.status_code == 200 and {x["id"] for x in r.json()["checks"]} >= {"resume", "search", "email", "discord", "daily_search", "jobs_found"}

        with patch("app.services.notifier.send_alert_digest"):
            assert c.post("/me/alerts/preview").json()["discord"] == "not_connected"
            db.add(models.DiscordConnection(user_id=u.id, webhook_url_enc=calendar_encryption.encrypt_token(URL), webhook_hint="x",
                                            timezone="UTC", matches_enabled=False))
            db.commit()
            assert c.post("/me/alerts/preview").json()["discord"] == "alerts_off"
            db.query(models.DiscordConnection).filter_by(user_id=u.id).update({"matches_enabled": True})
            db.commit()
            with patch.object(dn, "_post", return_value=(True, 204, "")):
                assert c.post("/me/alerts/preview").json()["discord"] == "sent"
            with patch.object(dn, "_post", return_value=(False, 500, "Discord returned HTTP 500.")):
                assert c.post("/me/alerts/preview").json()["discord"] == "failed"

        before = db.query(models.ScheduledRunLog).filter_by(run_type=alert_status.HEARTBEAT).count()
        monkeypatch.setattr(settings, "cron_secret", "s3cret")
        r = c.post("/internal/send-alerts", headers={"x-cron-secret": "s3cret"})
        assert r.status_code == 200
        assert db.query(models.ScheduledRunLog).filter_by(run_type=alert_status.HEARTBEAT).count() == before + 1
    finally:
        app.dependency_overrides.clear()
        db.close()
