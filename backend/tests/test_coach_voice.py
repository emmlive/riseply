"""Career Coach 'read aloud' mode: the coach writes for the ear, and any
markdown or symbols that slip through are stripped before storing."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import career_coach as cc


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _client():
    db = SessionLocal()
    u = models.User(email=f"voice{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", resume_text="Security engineer.")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()

    from app.database import get_db
    from fastapi import Depends

    def _u(db=Depends(get_db)):
        return db.get(models.User, uid)
    app.dependency_overrides[get_current_user] = _u
    return TestClient(app)


def test_plain_for_voice_removes_symbols_but_keeps_markers():
    text = (
        "Think of it as **five boxes** — each one feeds the next:\n\n"
        "- **First** → know the system & its data\n"
        "* Second: rank 50% of risks, AI/ML included\n"
        "---\n"
        "## Why it matters \U0001F600\n"
        "[[visual]]{\"kind\":\"flow\",\"title\":\"**keep**\",\"steps\":[]}[[/visual]]\n"
        "See https://example.com/x and `code`."
    )
    out = cc.plain_for_voice(text)
    for bad in ("**", "→", "&", "%", "—", "---", "##", "`", "https://", "\U0001F600"):
        assert bad not in out.replace('"title":"**keep**"', "")
    assert "five boxes, each one feeds the next:" in out
    assert "50 percent of risks, AI ML included" in out
    assert "know the system and its data" in out
    assert '[[visual]]{"kind":"flow","title":"**keep**","steps":[]}[[/visual]]' in out   # diagram block untouched
    assert "\n\n\n" not in out


def test_plain_for_voice_leaves_normal_words_alone():
    assert cc.plain_for_voice("Use snake_case names, e.g. user_id, and plan 3-5 steps.") == \
        "Use snake_case names, e.g. user_id, and plan 3-5 steps."


def test_voice_flag_reaches_the_coach_and_cleans_the_reply():
    client = _client()
    seen = {}

    def fake_start(session_type, role, topic, resume, library=None, learning_style="auto", voice=False):
        seen["start_voice"] = voice
        return {"topic": "Threat modeling", "opening_message": "Let's begin **now** → ready?"}

    def fake_reply(*args, voice=False, **kwargs):
        seen["reply_voice"] = voice
        return "Great answer.\n\n- **First**, rank the risks.\n---\nNext step."

    with patch("app.routers.career_coach.career_coach_service.start_session", side_effect=fake_start), \
         patch("app.routers.career_coach.career_coach_service.reply", side_effect=fake_reply):
        started = client.post("/career-coach/sessions", json={
            "session_type": "drill", "target_role": "Security Architect", "voice": True})
        assert started.status_code == 200, started.text
        assert seen["start_voice"] is True
        assert started.json()["opening_message"]["content"] == "Let's begin now, ready?"

        sid = started.json()["session"]["id"]
        sent = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "I'd start with assets", "voice": True})
        assert sent.status_code == 200, sent.text
        assert seen["reply_voice"] is True
        assert sent.json()["content"] == "Great answer.\n\nFirst, rank the risks.\n\nNext step."

        # Without voice mode nothing is rewritten.
        plain = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "and then?"})
        assert plain.json()["content"].startswith("Great answer.\n\n- **First**")
        assert seen["reply_voice"] is False
