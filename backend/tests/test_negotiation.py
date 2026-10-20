"""Salary negotiation role-play: the coach plays the recruiter, stays in
character, invents no real market figures, and scores the approach."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import career_coach as cc


def _resp(text="TOPIC: Offer negotiation\n---\nCongratulations, we'd love to have you. We can offer a base of 100,000 dollars."):
    r = MagicMock(); r.content = [MagicMock(text=text)]; return r


def _prompt(fn, *args, **kwargs):
    with patch.object(cc.client.messages, "create", return_value=_resp()) as create:
        fn(*args, **kwargs)
    call = create.call_args.kwargs
    return (call.get("system") or "") + " ".join(m["content"] for m in call["messages"] if isinstance(m["content"], str))


def test_opening_prompt_makes_the_coach_the_recruiter_with_made_up_figures():
    p = _prompt(cc.start_session, "negotiation", "Security Analyst", "", "Resume")
    assert "RECRUITER" in p and "Stay in character" in p
    assert "made-up practice figures" in p and "never real market pay" in p
    # in-character: no coaching cards and no tool-teaching block
    assert "TEACH WITH REAL TOOLS" not in p and "ROLE-PLAY NOTE" in p


def test_reply_prompt_holds_firm_stays_honest_and_steps_out_properly():
    p = _prompt(cc.reply, "negotiation", "Security Analyst", "t", "Resume", [], "I'd like 120k")
    assert "concede only when they earn it" in p
    assert "Never suggest that they claim something false" in p
    assert "[Stepping out of the negotiation]" in p and "professional about contract terms" in p
    assert "TEACH WITH REAL TOOLS" not in p


def test_a_recruiter_may_open_with_great_or_perfect():
    raw = "Great, that works for us. Let's talk about the start date next."
    assert cc.strip_praise_opener(raw, "negotiation") == raw


def test_scoring_judges_the_approach_not_the_outcome_and_never_advises_lying():
    hist = [{"role": "assistant", "content": "We offer 100k."}, {"role": "user", "content": "Could we discuss 115k given my audit scope?"}]
    p = _prompt(cc.finish_session, "negotiation", "Security Analyst", "Offer negotiation", "Resume", hist)
    assert "Judge the approach, not whether the" in p and "never advise saying anything untrue" in p


@pytest.fixture()
def client():
    db = SessionLocal()
    user = models.User(email=f"ng-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="Auditor.")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db
    app.dependency_overrides.clear()
    db.close()


def test_a_negotiation_session_can_be_started_and_continued(client):
    c, user, db = client
    with patch.object(cc.client.messages, "create", return_value=_resp()):
        r = c.post("/career-coach/sessions", json={"session_type": "negotiation", "target_role": "Security Analyst"})
    assert r.status_code == 200, r.text
    assert r.json()["session"]["session_type"] == "negotiation"
    assert r.json()["session"]["topic"] == "Offer negotiation"
    sid = r.json()["session"]["id"]
    with patch("app.services.career_coach.reply", return_value="Great, I hear you. Let me see what I can do on base."):
        m = c.post(f"/career-coach/sessions/{sid}/messages", json={"message": "Can we revisit the base?"})
    assert m.status_code == 200 and m.json()["content"].startswith("Great, I hear you")   # not stripped: in character


def test_unknown_session_types_are_still_rejected(client):
    c, *_ = client
    assert c.post("/career-coach/sessions", json={"session_type": "haggling", "target_role": "Analyst"}).status_code == 422
