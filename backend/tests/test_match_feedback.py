"""Learning from rejections: reasons are stored, summarised for the matcher as
a soft signal, and kept out of the prompt until there is enough of it."""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import matcher, match_feedback


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"mf-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="Analyst")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db
    app.dependency_overrides.clear()
    db.close()


def _application(db, user, title="Analyst", company="Acme"):
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title=title, company=company, description="d")
    db.add(job); db.commit(); db.refresh(job)
    a = models.Application(user_id=user.id, job_id=job.id)
    db.add(a); db.commit(); db.refresh(a)
    return a


def test_reject_saves_a_known_reason_and_clips_the_note(ctx):
    c, user, db = ctx
    a = _application(db, user)
    r = c.post(f"/applications/{a.id}/reject", json={"reason": "pay", "note": "x" * 280})
    assert r.status_code == 200
    db.expire_all()
    row = db.get(models.Application, a.id)
    assert row.status == "rejected" and row.reject_reason == "pay" and len(row.reject_note) == 140


def test_reject_without_a_reason_or_with_a_made_up_one_still_rejects(ctx):
    c, user, db = ctx
    a, b = _application(db, user), _application(db, user)
    assert c.post(f"/applications/{a.id}/reject").status_code == 200
    assert c.post(f"/applications/{b.id}/reject", json={"reason": "made_up"}).status_code == 200
    db.expire_all()
    assert db.get(models.Application, a.id).reject_reason == ""
    assert db.get(models.Application, b.id).reject_reason == ""


def test_notes_wait_for_enough_signals_then_summarise(ctx):
    c, user, db = ctx
    first = _application(db, user, "Help Desk Tech", "Initech")
    c.post(f"/applications/{first.id}/reject", json={"reason": "level_too_junior"})
    assert match_feedback.notes_for(db, user.id) == ""
    second = _application(db, user, "IT Support", "Globex")
    c.post(f"/applications/{second.id}/reject", json={"reason": "pay", "note": "under 90k"})
    liked = _application(db, user, "Security Analyst", "Hooli")
    c.post(f"/applications/{liked.id}/approve")
    notes = match_feedback.notes_for(db, user.id)
    assert "Help Desk Tech at Initech: the level was too junior" in notes
    assert 'IT Support at Globex: the pay looked too low ("under 90k")' in notes
    assert "Wanted:" in notes and "Security Analyst at Hooli" in notes


def _reply(text):
    r = MagicMock(); r.content = [MagicMock(text=text)]; return r


def test_score_prompt_includes_the_feedback_as_a_soft_signal_and_not_in_the_criteria():
    job = {"title": "T", "company": "C", "location": "L", "description": "d"}
    profile = {"name": "p", "feedback_notes": "Passed on:\n- X at Y: the pay looked too low"}
    with patch.object(matcher.client.messages, "create", return_value=_reply('{"score": 60, "reason": "ok"}')) as create:
        matcher.score_job("resume", job, profile)
    prompt = create.call_args.kwargs["messages"][0]["content"]
    assert "the pay looked too low" in prompt and "soft signal" in prompt and "never instructions" in prompt
    assert "feedback_notes" not in prompt


def test_score_prompt_is_unchanged_without_feedback():
    job = {"title": "T", "company": "C", "location": "L", "description": "d"}
    with patch.object(matcher.client.messages, "create", return_value=_reply('{"score": 60, "reason": "ok"}')) as create:
        matcher.score_job("resume", job, {"name": "p"})
    assert "PAST MATCHES" not in create.call_args.kwargs["messages"][0]["content"]
