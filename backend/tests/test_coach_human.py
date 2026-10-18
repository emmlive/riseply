"""The coach talks like a person: no stock-praise openers, a tone block in
every prompt, and no quote-block symbols read out loud."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import career_coach as cc


@pytest.mark.parametrize("raw,expected", [
    ("Perfect. Let's work through a real scenario.", "Let's work through a real scenario."),
    ("Great job! You caught the odd hour, and that matters here.", "You caught the odd hour, and that matters here."),
    ("Great, let's look at the logs next because that is where the story is.", "Let's look at the logs next because that is where the story is."),
    ("Nice job. Excellent. Now consider the source address and where it sits.", "Now consider the source address and where it sits."),
    ("Good. Now the next step is to check the logs for that account.", "Now the next step is to check the logs for that account."),
])
def test_stock_praise_openers_are_cut(raw, expected):
    assert cc.strip_praise_opener(raw, "drill") == expected


@pytest.mark.parametrize("raw", [
    "You caught the odd hour, which is the right first instinct.",     # specific, and not an opener
    "Good luck with the interview prep; here is the plan for the week.",
    "Right, so the first thing is the baseline of normal logins here.",
    "Perfect.",                                                         # never cut a reply to nothing
    "[[cue:remember]] Great idea but keep it short and clear please",
    "Nice work on the rewrite; the second bullet still lacks a number.",
])
def test_everything_else_is_left_alone(raw):
    assert cc.strip_praise_opener(raw, "walkthrough") == raw


def test_a_mock_interviewer_may_say_great_thanks():
    raw = "Great, thanks for coming in today. Tell me about a time you led a project."
    assert cc.strip_praise_opener(raw, "interview") == raw


def test_quote_markers_are_not_read_aloud():
    assert cc.plain_for_voice("> Alert: failed logins\n> Account: jsmith") == "Alert: failed logins\nAccount: jsmith"


def _captured_prompt(fn, *args, **kwargs):
    resp = MagicMock()
    resp.content = [MagicMock(text="TOPIC: x\n---\nhello there friend, welcome to the session")]
    with patch.object(cc.client.messages, "create", return_value=resp) as create:
        fn(*args, **kwargs)
    call = create.call_args.kwargs
    return (call.get("system") or "") + " ".join(m["content"] for m in call["messages"] if isinstance(m["content"], str))


def test_every_prompt_carries_the_human_tone_block():
    start = _captured_prompt(cc.start_session, "drill", "Analyst", "", "Resume text")
    reply = _captured_prompt(cc.reply, "walkthrough", "Analyst", "t", "Resume text", [], "my answer")
    for prompt in (start, reply):
        assert "SOUND LIKE A PERSON" in prompt and "Never open with stock praise" in prompt
    assert "affirm what's" not in reply


@pytest.fixture()
def client():
    db = SessionLocal()
    user = models.User(email=f"hu-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="Engineer.")
    db.add(user); db.commit(); db.refresh(user)
    sess = models.CareerCoachSession(user_id=user.id, session_type="walkthrough", target_role="Analyst", topic="Triage", status="in_progress")
    db.add(sess); db.commit(); db.refresh(sess)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), sess
    app.dependency_overrides.clear()
    db.close()


def test_the_reply_endpoint_cuts_a_praise_opener(client):
    c, sess = client
    with patch("app.services.career_coach.reply", return_value="Perfect. You spotted the 2:47 AM login, and that is the right place to start."):
        r = c.post(f"/career-coach/sessions/{sess.id}/messages", json={"message": "The login time looks odd."})
    assert r.status_code == 200, r.text
    assert r.json()["content"].startswith("You spotted the 2:47 AM login")
