"""Tests for Discord momentum notifications (/discord/*, services/
discord_notify.py, /internal/discord-nudges). Discord itself is never
contacted: the low-level _post is patched everywhere.
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.rate_limit import limiter
from app.security import get_current_user
from app import models
from app.services import calendar_encryption
from app.services import discord_notify as dn

client = TestClient(app)
_n = [0]
URL = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123456789ABCD"
POST = "app.services.discord_notify._post"
OK = (True, 204, "")


@pytest.fixture()
def db():
    s = SessionLocal()
    s.query(models.DiscordConnection).delete()
    s.commit()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset():
    limiter.reset()
    yield
    app.dependency_overrides.clear()


def _user(db, suspended=False):
    _n[0] += 1
    u = models.User(email=f"dc{_n[0]}@x.com", hashed_password="x", full_name="T", resume_text="Analyst.", is_suspended=suspended)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(u):
    from fastapi import Depends
    from app.database import get_db
    uid = u.id

    def override(db=Depends(get_db)):
        return db.query(models.User).filter_by(id=uid).first()

    app.dependency_overrides[get_current_user] = override


def _conn(db, user, **over):
    c = models.DiscordConnection(
        user_id=user.id, webhook_url_enc=calendar_encryption.encrypt_token(URL),
        webhook_hint=dn.hint_for(URL), timezone="UTC", nudge_hour=18, **over,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _practice(db, user, when: datetime, role="Data Analyst"):
    """One coach session with a user message at `when` (naive UTC)."""
    s = models.CareerCoachSession(user_id=user.id, session_type="drill", target_role=role, topic="Joins", created_at=when)
    db.add(s)
    db.commit()
    db.add(models.CareerCoachMessage(session_id=s.id, user_id=user.id, role="user", content="x", created_at=when))
    db.commit()
    return s


WED_6PM = datetime(2026, 10, 7, 18, 30)   # a Wednesday
SUN_6PM = datetime(2026, 10, 11, 18, 30)  # the following Sunday


# ---- webhook validation -----------------------------------------------------

@pytest.mark.parametrize("url", [
    URL,
    "https://ptb.discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
    "https://discordapp.com/api/v10/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
])
def test_accepts_real_webhook_urls(url):
    assert dn.parse_webhook(url)


@pytest.mark.parametrize("url", [
    "http://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
    "https://discord.com.evil.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
    "https://evil.com/discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
    "https://user@discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
    "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123?x=1",
    "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123/extra",
    "https://localhost/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123",
    "https://169.254.169.254/latest/meta-data",
    "",
])
def test_rejects_anything_that_could_be_ssrf(url):
    assert dn.parse_webhook(url) is None
    assert dn._post(url, {})[0] is False  # and _post refuses before any network call


# ---- connect / manage -------------------------------------------------------

def test_connect_tests_the_webhook_stores_it_encrypted_and_never_returns_it(db):
    user = _user(db)
    _login(user)
    with patch(POST, return_value=OK) as post:
        r = client.put("/discord/connect", json={"webhook_url": URL, "timezone": "America/Chicago"})
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] and body["enabled"] and body["timezone"] == "America/Chicago"
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in r.text
    assert post.call_args.args[0] == URL  # a real test message went out first
    row = db.query(models.DiscordConnection).filter_by(user_id=user.id).first()
    assert row.webhook_url_enc != URL and URL not in row.webhook_url_enc
    assert calendar_encryption.decrypt_token(row.webhook_url_enc) == URL
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in client.get("/discord").text


def test_connect_rejections_save_nothing(db):
    user = _user(db)
    _login(user)
    assert client.put("/discord/connect", json={"webhook_url": "https://example.com/hook" + "x" * 10}).status_code == 400
    assert client.put("/discord/connect", json={"webhook_url": URL, "timezone": "Mars/Base"}).status_code == 400
    with patch(POST, return_value=(False, 404, "gone")):
        r = client.put("/discord/connect", json={"webhook_url": URL})
    assert r.status_code == 400 and "doesn't exist" in r.json()["detail"]
    with patch(POST, return_value=(False, 500, "boom")):
        assert client.put("/discord/connect", json={"webhook_url": URL}).status_code == 400
    assert db.query(models.DiscordConnection).filter_by(user_id=user.id).count() == 0


def test_connect_without_server_encryption_key_fails_clearly(db, monkeypatch):
    user = _user(db)
    _login(user)
    monkeypatch.setattr(settings, "calendar_token_encryption_key", "")
    with patch(POST, return_value=OK) as post:
        r = client.put("/discord/connect", json={"webhook_url": URL})
    assert r.status_code == 503 and "CALENDAR_TOKEN_ENCRYPTION_KEY" in r.json()["detail"]
    post.assert_not_called()


def test_settings_test_message_and_disconnect(db):
    user = _user(db)
    _login(user)
    assert client.get("/discord").json()["connected"] is False
    assert client.patch("/discord/settings", json={"nudge_hour": 9}).status_code == 404
    _conn(db, user)
    r = client.patch("/discord/settings", json={"nudge_hour": 9, "matches_enabled": True, "progress_enabled": False, "timezone": "Europe/London"})
    assert r.json()["nudge_hour"] == 9 and r.json()["matches_enabled"] is True and r.json()["progress_enabled"] is False
    assert client.patch("/discord/settings", json={"nudge_hour": 24}).status_code == 422
    assert client.patch("/discord/settings", json={"timezone": "Nope/Nope"}).status_code == 400
    with patch(POST, return_value=OK):
        assert client.post("/discord/test").json() == {"sent": True}
    with patch(POST, return_value=(False, 500, "x")):
        assert client.post("/discord/test").status_code == 502
    assert client.delete("/discord").json()["disconnected"] is True
    assert client.get("/discord").json()["connected"] is False
    assert client.delete("/discord").status_code == 200  # idempotent


def test_connections_are_private_per_user(db):
    a, b = _user(db), _user(db)
    _conn(db, a)
    _login(b)
    assert client.get("/discord").json()["connected"] is False
    assert client.delete("/discord").status_code == 200
    assert db.query(models.DiscordConnection).filter_by(user_id=a.id).count() == 1


# ---- delivery bookkeeping ---------------------------------------------------

def test_dead_webhook_is_switched_off_immediately(db):
    c = _conn(db, _user(db))
    with patch(POST, return_value=(False, 404, "gone")):
        assert dn.send(db, c, {}) is False
    db.refresh(c)
    assert c.enabled is False and "no longer exists" in c.last_error


def test_repeated_failures_switch_off_but_rate_limits_do_not_count(db):
    c = _conn(db, _user(db))
    with patch(POST, return_value=(False, 429, "slow")):
        for _ in range(10):
            dn.send(db, c, {})
    db.refresh(c)
    assert c.enabled and c.consecutive_failures == 0
    with patch(POST, return_value=(False, 500, "boom")):
        for _ in range(dn.MAX_FAILURES):
            dn.send(db, c, {})
    db.refresh(c)
    assert c.enabled is False
    # re-enabling resets the failure state
    _login(db.query(models.User).filter_by(id=c.user_id).first())
    assert client.patch("/discord/settings", json={"enabled": True}).json()["last_error"] == ""


def test_success_resets_failures(db):
    c = _conn(db, _user(db))
    c.consecutive_failures = 3
    db.commit()
    with patch(POST, return_value=OK):
        assert dn.send(db, c, {}) is True
    db.refresh(c)
    assert c.consecutive_failures == 0 and c.last_success_at


def test_payload_cannot_ping_anyone():
    p = dn.build_payload("hi @everyone", "ping @here and <@123456789> and <@&99>", fields=[("a", "@everyone")])
    assert p["allowed_mentions"] == {"parse": []}
    text = str(p)
    assert "@everyone" not in text and "@here" not in text and "<@" not in text
    assert len(dn.build_payload("t", "x" * 5000)["embeds"][0]["description"]) <= 1800


# ---- streaks and nudge rules -----------------------------------------------

def test_streak_counts_consecutive_days_and_survives_until_midnight():
    today = date(2026, 10, 7)
    days = {today - timedelta(days=i) for i in (1, 2, 3)}
    assert dn.streak_days(days, today) == 3            # not practiced yet today: still alive
    assert dn.streak_days(days | {today}, today) == 4
    assert dn.streak_days({today - timedelta(days=2)}, today) == 0  # broken
    assert dn.streak_days(set(), today) == 0


def test_practice_dates_use_the_users_timezone(db):
    from zoneinfo import ZoneInfo
    user = _user(db)
    _practice(db, user, datetime(2026, 10, 7, 3, 30))   # 22:30 on the 6th in Chicago
    assert dn.practice_dates(db, user.id, ZoneInfo("America/Chicago"), WED_6PM) == {date(2026, 10, 6)}
    assert dn.practice_dates(db, user.id, ZoneInfo("UTC"), WED_6PM) == {date(2026, 10, 7)}


def test_should_nudge_backs_off_for_quiet_users():
    today = date(2026, 10, 30)
    assert dn.should_nudge(set(), today)                                   # never practiced: gentle invite
    assert not dn.should_nudge({today}, today)                             # already practiced
    assert dn.should_nudge({today - timedelta(days=5)}, today)
    assert dn.should_nudge({today - timedelta(days=18)}, today)            # 18 % 3 == 0
    assert not dn.should_nudge({today - timedelta(days=17)}, today)
    assert not dn.should_nudge({today - timedelta(days=31)}, today)        # given up


# ---- hourly job -------------------------------------------------------------

def test_nudge_sent_in_window_once_per_day(db):
    user = _user(db)
    c = _conn(db, user)
    with patch(POST, return_value=OK) as post:
        assert dn.run_nudges(db, WED_6PM)["discord_nudges_sent"] == 1
        assert dn.run_nudges(db, WED_6PM + timedelta(hours=1))["discord_nudges_sent"] == 0   # same local day
        assert post.call_count == 1
        assert dn.run_nudges(db, WED_6PM + timedelta(days=1))["discord_nudges_sent"] == 1     # next day
    db.refresh(c)
    assert c.last_nudge_date == date(2026, 10, 8)


def test_nothing_sent_outside_window_or_to_inactive_connections(db):
    on = _conn(db, _user(db))
    off = _conn(db, _user(db), enabled=False)
    muted = _conn(db, _user(db), nudge_enabled=False)
    suspended = _conn(db, _user(db, suspended=True))
    with patch(POST, return_value=OK) as post:
        assert dn.run_nudges(db, datetime(2026, 10, 7, 12, 0))["discord_nudges_sent"] == 0   # before the window
        assert dn.run_nudges(db, datetime(2026, 10, 7, 22, 0))["discord_nudges_sent"] == 0   # after the 3h window
        dn.run_nudges(db, WED_6PM)
    assert post.call_count == 1  # only `on`


def test_no_nudge_if_already_practiced_today_and_streak_warning_text(db):
    done = _user(db)
    at_risk = _user(db)
    _conn(db, done)
    _conn(db, at_risk)
    _practice(db, done, datetime(2026, 10, 7, 9, 0))
    for d in (6, 5, 4):
        _practice(db, at_risk, datetime(2026, 10, d, 9, 0), role="UX Designer")
    sent = []
    with patch(POST, side_effect=lambda url, payload: (sent.append(payload) or OK)):
        result = dn.run_nudges(db, WED_6PM)
    assert result["discord_nudges_sent"] == 1 and result["discord_skipped"] == 1
    embed = sent[0]["embeds"][0]
    assert "3-day streak" in embed["title"] and "UX Designer" in embed["description"]


def test_users_local_time_decides_the_window(db):
    user = _user(db)
    c = _conn(db, user)
    c.timezone = "America/Chicago"   # 18:30 UTC is 13:30 in Chicago (CDT)
    c.nudge_hour = 13
    db.commit()
    with patch(POST, return_value=OK) as post:
        assert dn.run_nudges(db, WED_6PM)["discord_nudges_sent"] == 1
    c.nudge_hour = 18
    c.last_nudge_date = None
    db.commit()
    with patch(POST, return_value=OK):
        assert dn.run_nudges(db, WED_6PM)["discord_nudges_sent"] == 0


def test_sunday_recap_replaces_nudge_and_sends_once_per_week(db):
    user = _user(db)
    c = _conn(db, user)
    s = _practice(db, user, datetime(2026, 10, 8, 10, 0))
    s.status, s.score, s.topic, s.completed_at = "completed", 62, "Window functions", datetime(2026, 10, 8, 10, 30)
    db.commit()
    sent = []
    with patch(POST, side_effect=lambda url, payload: (sent.append(payload) or OK)):
        res = dn.run_nudges(db, SUN_6PM)
        again = dn.run_nudges(db, SUN_6PM + timedelta(hours=1))
    assert res["discord_recaps_sent"] == 1 and res["discord_nudges_sent"] == 0
    assert again["discord_recaps_sent"] == 0 and len(sent) == 1
    text = sent[0]["embeds"][0]["description"]
    assert "62/100" in text and "Window functions" in text
    db.refresh(c)
    assert c.last_recap_week == "2026-W41"


def test_no_recap_for_a_week_with_no_activity_and_respects_toggle(db):
    quiet = _user(db)
    _conn(db, quiet)
    muted = _user(db)
    _conn(db, muted, progress_enabled=False)
    _practice(db, muted, datetime(2026, 10, 8, 10, 0))
    with patch(POST, return_value=OK) as post:
        res = dn.run_nudges(db, SUN_6PM)
    assert res["discord_recaps_sent"] == 0
    # Neither gets a recap; both fall back to the normal nudge (muting
    # recaps doesn't mute nudges, and `muted` hasn't practiced today).
    assert res["discord_nudges_sent"] == 2


def test_one_broken_connection_does_not_stop_the_run(db):
    a, b = _user(db), _user(db)
    bad = _conn(db, a)
    bad.timezone = "Not/AZone"   # falls back to UTC rather than crashing
    good = _conn(db, b)
    db.commit()
    with patch(POST, return_value=OK):
        assert dn.run_nudges(db, WED_6PM)["discord_nudges_sent"] == 2


def test_internal_endpoint_requires_the_cron_secret(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    assert client.post("/internal/discord-nudges").status_code == 401
    r = client.post("/internal/discord-nudges", headers={"X-Cron-Secret": "s3cret"})
    assert r.status_code == 200 and "discord_nudges_sent" in r.json()
    monkeypatch.setattr(settings, "cron_secret", "")
    assert client.post("/internal/discord-nudges").status_code == 503


# ---- follow-up after a coaching session ------------------------------------

def test_session_follow_up_goes_to_discord_with_a_library_resource(db):
    user = _user(db)
    _conn(db, user)
    item = models.LibraryItem(title="Zymurgy Basics", url="https://example.com/zymurgy", description="Brewing science.",
                              resource_type="course", fields="zymurgy", level="beginner", cost="free", active=True)
    db.add(item)
    db.commit()
    s = _practice(db, user, datetime.utcnow(), role="Zymurgy Brewer")
    s.status, s.score, s.feedback = "completed", 74, "Good fundamentals; practice edge cases."
    db.commit()
    sent = []
    with patch(POST, side_effect=lambda url, payload: (sent.append(payload) or OK)):
        dn.send_session_followup(s.id)
    embed = sent[0]["embeds"][0]
    assert "74/100" in str(embed["fields"]) and "practice edge cases" in embed["description"]
    assert "[Zymurgy Basics](https://example.com/zymurgy)" in embed["description"]


def test_follow_up_respects_toggles_and_missing_connection(db):
    user = _user(db)
    s = _practice(db, user, datetime.utcnow())
    with patch(POST, return_value=OK) as post:
        dn.send_session_followup(s.id)                   # no connection
        dn.send_session_followup(99999999)               # no session
        c = _conn(db, user, followup_enabled=False)
        dn.send_session_followup(s.id)                   # muted
    post.assert_not_called()


def test_completing_a_session_triggers_the_follow_up(db):
    user = _user(db)
    _conn(db, user)
    _login(user)
    with patch("app.routers.career_coach.career_coach_service.start_session", return_value={"topic": "Joins", "opening_message": "Q?"}):
        sid = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Data Analyst"}).json()["session"]["id"]
    with patch("app.routers.career_coach.career_coach_service.reply", return_value="ok"):
        client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "answer"})
    sent = []
    with patch("app.routers.career_coach.career_coach_service.finish_session", return_value={"score": 88, "feedback": "Strong."}), \
         patch(POST, side_effect=lambda url, payload: (sent.append(payload) or OK)):
        assert client.post(f"/career-coach/sessions/{sid}/complete").status_code == 200
    assert len(sent) == 1 and "88/100" in str(sent[0])


# ---- job matches ------------------------------------------------------------

def test_matches_only_go_to_discord_when_opted_in(db):
    user = _user(db)
    c = _conn(db, user)  # matches_enabled defaults to False
    job = {"title": "Data Analyst", "company": "Acme", "match_score": 91, "match_reason": "Strong SQL.", "location": "Remote", "url": "https://acme.com/j"}
    with patch(POST, return_value=OK) as post:
        dn.notify_new_match(db, user, job)
        dn.notify_digest(db, user, [job])
        post.assert_not_called()
        c.matches_enabled = True
        db.commit()
        dn.notify_new_match(db, user, job)
        dn.notify_digest(db, user, [job, job])
        dn.notify_digest(db, user, [])
    assert post.call_count == 2
