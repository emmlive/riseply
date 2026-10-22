"""Session clock: time limit at start, time spent saved by the page, pacing note for the coach."""
import uuid
from unittest.mock import patch

from app import models
from app.services import career_coach as cc
from tests.test_career_coach import client, _login_as, SVC, db, _clear_overrides  # noqa: F401
from tests.test_coach_courses import _course, _start_module, CC  # noqa: F401


def _user(db):
    u = models.User(email=f"clk{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T", resume_text="Support specialist")
    db.add(u); db.commit(); db.refresh(u)
    _login_as(u)
    return u


def _start(limit=None):
    body = {"session_type": "drill", "target_role": "Data Analyst", "topic": ""}
    if limit is not None:
        body["time_limit_min"] = limit
    with patch(f"{SVC}.start_session", return_value={"topic": "SQL", "opening_message": "Hi"}):
        return client.post("/career-coach/sessions", json=body).json()["session"]


def test_limit_is_chosen_at_start_and_defaults_to_none(db):
    _user(db)
    assert _start()["time_limit_min"] == 0
    assert _start(30)["time_limit_min"] == 30
    assert client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Data Analyst", "time_limit_min": 999}).status_code == 422


def test_module_session_defaults_to_the_modules_length(db):
    _user(db)
    cid = _course().json()["id"]
    assert _start_module(cid)[0].json()["session"]["time_limit_min"] == 40


def test_clock_only_goes_up_in_small_steps_and_limit_can_change(db):
    _user(db)
    s = _start(15)
    url = f"/career-coach/sessions/{s['id']}/clock"
    assert client.put(url, json={"active_seconds": 120}).json()["active_seconds"] == 120
    assert client.put(url, json={"active_seconds": 60}).json()["active_seconds"] == 120      # never goes back
    assert client.put(url, json={"active_seconds": 80000}).json()["active_seconds"] == 720   # at most +10 min per report
    assert client.put(url, json={"active_seconds": 800, "time_limit_min": 25}).json()["time_limit_min"] == 25


def test_clock_is_private(db):
    _user(db)
    s = _start()
    _user(db)
    assert client.put(f"/career-coach/sessions/{s['id']}/clock", json={"active_seconds": 5}).status_code == 404


def test_minutes_left_reaches_the_coach_and_time_note_only_when_short():
    assert cc.time_note(None) == "" and cc.time_note(20) == ""
    assert "3 minutes left" in cc.time_note(3) and "up" in cc.time_note(0)


def test_minutes_left_is_passed_to_reply(db):
    _user(db)
    s = _start(10)
    with patch(f"{SVC}.reply", return_value="ok") as r:
        res = client.post(f"/career-coach/sessions/{s['id']}/messages", json={"message": "hi", "minutes_left": 2})
    assert res.status_code == 200 and r.call_args.kwargs["minutes_left"] == 2


def test_timer_can_be_paused_stopped_and_restarted(db):
    _user(db)
    s = _start(30)
    url = f"/career-coach/sessions/{s['id']}/clock"
    assert s["timer_state"] == ""
    for state in ("paused", "running", "stopped"):
        assert client.put(url, json={"active_seconds": 10, "timer_state": state}).json()["timer_state"] == state
    assert client.put(url, json={"active_seconds": 10, "timer_state": "bogus"}).status_code == 422
    assert client.put(url, json={"active_seconds": 20}).json()["timer_state"] == "stopped"   # left alone when not sent
