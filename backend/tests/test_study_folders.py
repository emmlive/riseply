"""Study folders and saved Career Coach notes."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, get_db
from app import models
from app.security import get_current_user


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _user():
    db = SessionLocal()
    u = models.User(email=f"study{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", resume_text="r")
    db.add(u)
    db.commit()
    uid = u.id
    s = models.CareerCoachSession(user_id=uid, session_type="drill", target_role="Architect", topic="STRIDE")
    db.add(s)
    db.commit()
    sid = s.id
    db.close()
    return uid, sid


def _as(uid):
    from fastapi import Depends

    def _u(db=Depends(get_db)):
        return db.get(models.User, uid)
    app.dependency_overrides[get_current_user] = _u
    return TestClient(app)


def test_folder_lifecycle_and_names():
    uid, _ = _user()
    c = _as(uid)
    a = c.post("/career-coach/study/folders", json={"name": "  Threat   modeling "})
    assert a.status_code == 201 and a.json()["name"] == "Threat modeling" and a.json()["note_count"] == 0
    assert c.post("/career-coach/study/folders", json={"name": "threat MODELING"}).status_code == 409
    b = c.post("/career-coach/study/folders", json={"name": "Interview stories"}).json()

    assert [f["name"] for f in c.get("/career-coach/study/folders").json()] == ["Interview stories", "Threat modeling"]
    assert c.patch(f"/career-coach/study/folders/{b['id']}", json={"name": "Stories"}).json()["name"] == "Stories"
    assert c.patch(f"/career-coach/study/folders/{b['id']}", json={"name": "Threat modeling"}).status_code == 409
    assert c.post("/career-coach/study/folders", json={"name": "   "}).status_code == 422


def test_notes_save_move_edit_and_delete_folder_keeps_notes():
    uid, sid = _user()
    c = _as(uid)
    folder = c.post("/career-coach/study/folders", json={"name": "STRIDE"}).json()

    saved = c.post("/career-coach/study/notes", json={
        "content": "Spoofing, Tampering, Repudiation...", "folder_id": folder["id"], "session_id": sid,
        "source": "notepad", "source_label": "Drill · Architect", "title": "STRIDE recap"})
    assert saved.status_code == 201
    note = saved.json()
    assert note["title"] == "STRIDE recap" and note["folder_id"] == folder["id"]

    # No title: it's taken from the first line.
    auto = c.post("/career-coach/study/notes", json={"content": "First line here\nsecond line"}).json()
    assert auto["title"] == "First line here" and auto["folder_id"] is None

    assert [n["id"] for n in c.get(f"/career-coach/study/notes?folder_id={folder['id']}").json()] == [note["id"]]
    assert [n["id"] for n in c.get("/career-coach/study/notes?unfiled=true").json()] == [auto["id"]]
    assert len(c.get("/career-coach/study/notes").json()) == 2
    assert c.get("/career-coach/study/folders").json()[0]["note_count"] == 1

    edited = c.patch(f"/career-coach/study/notes/{note['id']}", json={"content": "Edited"}).json()
    assert edited["content"] == "Edited" and edited["folder_id"] == folder["id"]          # untouched fields stay
    moved = c.patch(f"/career-coach/study/notes/{note['id']}", json={"folder_id": None}).json()
    assert moved["folder_id"] is None                                                       # explicit null = Unfiled
    c.patch(f"/career-coach/study/notes/{note['id']}", json={"folder_id": folder["id"]})

    assert c.delete(f"/career-coach/study/folders/{folder['id']}").status_code == 204
    kept = c.get("/career-coach/study/notes?unfiled=true").json()
    assert note["id"] in [n["id"] for n in kept]                                            # notes survive their folder

    assert c.delete(f"/career-coach/study/notes/{note['id']}").status_code == 204
    assert c.patch(f"/career-coach/study/notes/{note['id']}", json={"title": "x"}).status_code == 404


def test_validation_and_privacy():
    uid, sid = _user()
    other, other_sid = _user()
    c = _as(uid)
    mine = c.post("/career-coach/study/folders", json={"name": "Mine"}).json()
    note = c.post("/career-coach/study/notes", json={"content": "private"}).json()

    assert c.post("/career-coach/study/notes", json={"content": "   "}).status_code == 422
    assert c.post("/career-coach/study/notes", json={"content": "x", "source": "bogus"}).status_code == 422
    assert c.post("/career-coach/study/notes", json={"content": "x", "folder_id": 99999999}).status_code == 404
    assert c.post("/career-coach/study/notes", json={"content": "x", "session_id": other_sid}).status_code == 404
    assert c.patch(f"/career-coach/study/notes/{note['id']}", json={"content": "  "}).status_code == 422

    c2 = _as(other)
    assert c2.get("/career-coach/study/notes").json() == []
    assert c2.get("/career-coach/study/folders").json() == []
    assert c2.patch(f"/career-coach/study/notes/{note['id']}", json={"title": "hijack"}).status_code == 404
    assert c2.delete(f"/career-coach/study/notes/{note['id']}").status_code == 404
    assert c2.delete(f"/career-coach/study/folders/{mine['id']}").status_code == 404
    assert c2.post("/career-coach/study/notes", json={"content": "x", "folder_id": mine["id"]}).status_code == 404
