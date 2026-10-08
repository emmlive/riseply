"""Memory cues: the coach may pin a line to an object card. The server keeps
the marker format strict and caps it at two per reply."""
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
    u = models.User(email=f"cue{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", resume_text="Security engineer.")
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


def test_limit_cues_keeps_two_valid_lines_and_drops_the_rest_of_the_markers():
    text = (
        "Good start.\n"
        "[[cue:remember]] Rank risks by likelihood and impact.\n"
        "More explanation.\n"
        "[[cue:write]] STRIDE has six threat types.\n"
        "[[cue:watch]] Third cue is one too many.\n"
    )
    out = cc.limit_cues(text)
    assert out.count("[[cue:") == 2
    assert "[[cue:remember]] Rank risks by likelihood and impact." in out
    assert "[[cue:write]] STRIDE has six threat types." in out
    assert "Third cue is one too many." in out and "[[cue:watch]]" not in out


def test_limit_cues_removes_malformed_markers_but_keeps_words():
    out = cc.limit_cues("Intro [[cue:remember]] mid-line.\n[[cue:banana]] Unknown kind.\n[[cue:try]]\n[[/cue]]")
    assert "[[" not in out
    assert "mid-line." in out and "Unknown kind." in out


def test_limit_cues_leaves_plain_replies_alone():
    assert cc.limit_cues("Nothing special here.") == "Nothing special here."


def test_cues_as_text_spells_out_the_label():
    assert cc.cues_as_text("Hi\n[[cue:remember]] Lock this in.") == "Hi\nRemember: Lock this in."
    assert cc.cues_as_text("[[cue:write]] A phrase") == "Write this down: A phrase"


def test_voice_cleanup_keeps_the_marker_and_cleans_the_words():
    out = cc.plain_for_voice("Fine.\n[[cue:remember]] Use **STRIDE** → every time.")
    assert "[[cue:remember]]" in out
    assert "**" not in out and "→" not in out
    assert "Use STRIDE, every time." in out


def test_interviews_get_no_cue_instructions():
    assert cc._cue_note("interview") == ""
    assert "[[cue:remember]]" in cc._cue_note("drill")


def test_endpoints_cap_cues_even_in_voice_mode():
    client = _client()
    opening = "Question first.\n[[cue:remember]] One.\n[[cue:write]] Two.\n[[cue:try]] Three."

    def fake_start(*a, **k):
        return {"topic": "Threat modeling", "opening_message": opening}

    def fake_reply(*a, **k):
        return "Nice.\n[[cue:watch]] **Do not** skip the data flow.\n[[cue:remember]] A.\n[[cue:write]] B."

    with patch("app.routers.career_coach.career_coach_service.start_session", side_effect=fake_start), \
         patch("app.routers.career_coach.career_coach_service.reply", side_effect=fake_reply):
        started = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Security Architect"})
        assert started.status_code == 200, started.text
        assert started.json()["opening_message"]["content"].count("[[cue:") == 2

        sid = started.json()["session"]["id"]
        sent = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "assets first", "voice": True})
        assert sent.status_code == 200, sent.text
        body = sent.json()["content"]
        assert body.count("[[cue:") == 2
        assert "**" not in body
        assert "[[cue:watch]] Do not skip the data flow." in body
