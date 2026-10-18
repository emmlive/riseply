"""Voice interview: spoken-answer delivery stats are validated, saved with the
answer, shown back on it, and used (only) in the end-of-session feedback."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models, schemas
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import career_coach as cc

STATS = {"seconds": 74, "words": 180, "wpm": 146, "fillers": {"you know": 3, "basically": 1}}


def test_delivery_stats_are_clamped_and_cleaned():
    d = schemas.DeliveryStats(seconds=10, words=20, wpm=120, fillers={"  ": 5, "x" * 50: 999, "like": -3})
    assert "  " not in d.fillers and d.fillers["x" * 24] == 200 and d.fillers["like"] == 0
    with pytest.raises(Exception):
        schemas.DeliveryStats(seconds=99999, words=1)


def test_delivery_line_lists_the_top_fillers():
    line = cc.delivery_line(schemas.DeliveryStats(**STATS))
    assert line.startswith("[spoken: 74s, 180 words, 146 words per minute")
    assert "you know x3" in line and "basically x1" in line
    assert "no filler phrases found" in cc.delivery_line(schemas.DeliveryStats(seconds=5, words=9, wpm=100))


def _reply(text):
    r = MagicMock(); r.content = [MagicMock(text=text)]; return r


def test_finish_prompt_includes_delivery_only_when_answers_were_spoken():
    hist = [{"role": "assistant", "content": "Tell me about yourself."},
            {"role": "user", "content": "I lead security audits.", "delivery": schemas.DeliveryStats(**STATS)}]
    with patch.object(cc.client.messages, "create", return_value=_reply("SCORE: 70\n---\nGood.")) as create:
        cc.finish_session("interview", "Analyst", "t", "resume", hist)
    prompt = create.call_args.kwargs["messages"][0]["content"]
    assert "[spoken: 74s" in prompt and "SPOKEN ANSWERS" in prompt and "NOT claim the person never uses them" in prompt

    typed = [{"role": "assistant", "content": "Q"}, {"role": "user", "content": "A"}]
    with patch.object(cc.client.messages, "create", return_value=_reply("SCORE: 70\n---\nGood.")) as create:
        cc.finish_session("interview", "Analyst", "t", "resume", typed)
    assert "SPOKEN ANSWERS" not in create.call_args.kwargs["messages"][0]["content"]


@pytest.fixture()
def client():
    db = SessionLocal()
    user = models.User(email=f"vi-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="Engineer.")
    db.add(user); db.commit(); db.refresh(user)
    sess = models.CareerCoachSession(user_id=user.id, session_type="interview", target_role="Analyst", topic="Behavioral", status="in_progress")
    db.add(sess); db.commit(); db.refresh(sess)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), sess, db
    app.dependency_overrides.clear()
    db.close()


def test_spoken_answer_is_saved_shown_back_and_scored(client):
    c, sess, db = client
    with patch("app.services.career_coach.reply", return_value="Walk me through a time you led a project."):
        r = c.post(f"/career-coach/sessions/{sess.id}/messages", json={"message": "I lead audits.", "voice": True, "delivery": STATS})
    assert r.status_code == 200, r.text
    msgs = c.get(f"/career-coach/sessions/{sess.id}/messages").json()
    mine = [m for m in msgs if m["role"] == "user"][0]
    assert mine["delivery"]["wpm"] == 146 and mine["delivery"]["fillers"]["you know"] == 3
    assert [m for m in msgs if m["role"] == "assistant"][0]["delivery"] is None

    with patch.object(cc.client.messages, "create", return_value=_reply("SCORE: 72\n---\nSolid; slow your pace slightly.")) as create:
        done = c.post(f"/career-coach/sessions/{sess.id}/complete")
    assert done.status_code == 200, done.text
    assert "[spoken: 74s" in create.call_args.kwargs["messages"][0]["content"]


def test_typed_answers_have_no_delivery(client):
    c, sess, db = client
    with patch("app.services.career_coach.reply", return_value="Next question please, thanks for that."):
        c.post(f"/career-coach/sessions/{sess.id}/messages", json={"message": "typed answer"})
    assert all(m["delivery"] is None for m in c.get(f"/career-coach/sessions/{sess.id}/messages").json())


def test_bad_delivery_numbers_are_rejected(client):
    c, sess, db = client
    r = c.post(f"/career-coach/sessions/{sess.id}/messages", json={"message": "x", "delivery": {"seconds": -1, "words": 5}})
    assert r.status_code == 422
