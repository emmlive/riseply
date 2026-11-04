"""Flag past coach sessions (continue / keep / not keeping) and delete them."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user


@pytest.fixture()
def setup():
    db = SessionLocal()
    mk = lambda: models.User(email=f"flag-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="x")
    me, other = mk(), mk()
    db.add_all([me, other]); db.commit()
    app.dependency_overrides[get_current_user] = lambda: me
    yield db, me, other, TestClient(app)
    app.dependency_overrides.clear(); db.close()


def _session(db, user, topic="T"):
    s = models.CareerCoachSession(user_id=user.id, session_type="drill", target_role="Security Architect", topic=topic)
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_flag_round_trip_and_validation(setup):
    db, me, other, client = setup
    s = _session(db, me)
    assert client.get("/career-coach/sessions").json()[0]["flag"] == ""
    for f in ("continue", "keep", "discard", ""):
        r = client.put(f"/career-coach/sessions/{s.id}/flag", json={"flag": f})
        assert r.status_code == 200 and r.json()["flag"] == f
    assert client.put(f"/career-coach/sessions/{s.id}/flag", json={"flag": "purple"}).status_code == 422
    theirs = _session(db, other)
    assert client.put(f"/career-coach/sessions/{theirs.id}/flag", json={"flag": "keep"}).status_code == 404
    assert client.delete(f"/career-coach/sessions/{theirs.id}").status_code == 404


def test_delete_removes_transcript_and_notepad_but_keeps_study_notes(setup):
    db, me, other, client = setup
    s = _session(db, me)
    db.add_all([
        models.CareerCoachMessage(session_id=s.id, user_id=me.id, role="user", content="hi"),
        models.CareerCoachNote(session_id=s.id, user_id=me.id, content="scratch"),
        models.StudyNote(user_id=me.id, session_id=s.id, title="kept note", content="c"),
    ])
    db.commit()
    sid = s.id
    assert client.delete(f"/career-coach/sessions/{sid}").status_code == 204
    db.expire_all()
    assert db.query(models.CareerCoachSession).filter_by(id=sid).first() is None
    assert db.query(models.CareerCoachMessage).filter_by(session_id=sid).count() == 0
    note = db.query(models.StudyNote).filter_by(user_id=me.id, title="kept note").first()
    assert note is not None and note.session_id is None


def test_delete_all_not_keeping_leaves_the_rest(setup):
    db, me, other, client = setup
    a, b, c = _session(db, me, "a"), _session(db, me, "b"), _session(db, me, "c")
    theirs = _session(db, other, "theirs")
    for s, f in ((a, "discard"), (b, "discard"), (c, "keep")):
        client.put(f"/career-coach/sessions/{s.id}/flag", json={"flag": f})
    theirs_id = theirs.id
    theirs.flag = "discard"; db.commit()
    assert client.post("/career-coach/sessions/delete-discarded").json() == {"deleted": 2}
    left = [x["topic"] for x in client.get("/career-coach/sessions").json()]
    assert left == ["c"]
    db.expire_all()
    assert db.query(models.CareerCoachSession).filter_by(id=theirs_id).first() is not None
