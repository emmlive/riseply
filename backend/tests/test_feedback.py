"""In-product feedback: the Give feedback button and thumbs on coach replies."""
import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, get_db
from app import models
from app.security import get_current_user


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _user(db, **kw):
    u = models.User(email=f"fb{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", **kw)
    db.add(u)
    db.commit()
    return u


def _as(uid):
    def _u(db=Depends(get_db)):
        return db.get(models.User, uid)
    app.dependency_overrides[get_current_user] = _u
    return TestClient(app)


def _reply(db, uid, role="assistant", text="Here is how to think about spoofing."):
    s = models.CareerCoachSession(user_id=uid, session_type="drill", target_role="IT Auditor", topic="x")
    db.add(s)
    db.commit()
    m = models.CareerCoachMessage(session_id=s.id, user_id=uid, role=role, content=text)
    db.add(m)
    db.commit()
    return s.id, m.id


def test_general_feedback_is_saved_and_needs_something_to_say():
    db = SessionLocal()
    u = _user(db)
    uid = u.id
    db.close()
    c = _as(uid)
    assert c.post("/feedback", json={"rating": 4, "category": "idea", "message": " Add dark mode ", "page": "/dashboard/progress"}).status_code == 201
    assert c.post("/feedback", json={"rating": 5}).status_code == 201                     # a rating alone is fine
    assert c.post("/feedback", json={"message": "Loving it"}).status_code == 201          # words alone are fine
    assert c.post("/feedback", json={}).status_code == 422                                # nothing
    assert c.post("/feedback", json={"rating": 6}).status_code == 422
    assert c.post("/feedback", json={"rating": 3, "category": "rant"}).status_code == 422
    assert c.post("/feedback", json={"message": "x" * 2001}).status_code == 422
    db = SessionLocal()
    row = db.query(models.Feedback).filter_by(user_id=uid, rating=4).one()
    assert row.message == "Add dark mode" and row.category == "idea" and row.kind == "general"
    db.close()


def test_general_feedback_is_rate_limited_per_day():
    db = SessionLocal()
    uid = _user(db).id
    db.close()
    c = _as(uid)
    for _ in range(20):
        assert c.post("/feedback", json={"rating": 3}).status_code == 201
    r = c.post("/feedback", json={"rating": 3})
    assert r.status_code == 429 and "tomorrow" in r.json()["detail"]


def test_thumbs_upsert_and_note_rules():
    db = SessionLocal()
    uid = _user(db).id
    sid, mid = _reply(db, uid)
    db.close()
    c = _as(uid)
    assert c.put("/feedback/coach-reply", json={"message_id": mid, "helpful": False, "note": " Too vague "}).json() == {"message_id": mid, "helpful": False}
    assert c.get(f"/feedback/coach-replies?session_id={sid}").json() == [{"message_id": mid, "helpful": False}]
    db = SessionLocal()
    rows = db.query(models.Feedback).filter_by(user_id=uid, message_id=mid).all()
    assert len(rows) == 1 and rows[0].message == "Too vague" and rows[0].session_id == sid
    db.close()
    # Changing their mind updates the same row and drops the old note.
    c.put("/feedback/coach-reply", json={"message_id": mid, "helpful": True, "note": "ignored"})
    db = SessionLocal()
    rows = db.query(models.Feedback).filter_by(user_id=uid, message_id=mid).all()
    assert len(rows) == 1 and rows[0].helpful is True and rows[0].message == ""
    db.close()


def test_thumbs_only_on_your_own_coach_replies():
    db = SessionLocal()
    me, other = _user(db).id, _user(db).id
    _, theirs = _reply(db, other)
    _, mine_user_turn = _reply(db, me, role="user", text="my answer")
    db.close()
    c = _as(me)
    assert c.put("/feedback/coach-reply", json={"message_id": theirs, "helpful": True}).status_code == 404
    assert c.put("/feedback/coach-reply", json={"message_id": mine_user_turn, "helpful": True}).status_code == 404
    assert c.put("/feedback/coach-reply", json={"message_id": 99999999, "helpful": True}).status_code == 404
    sid_other = _as(other).get("/feedback/coach-replies?session_id=1").json()
    assert sid_other == [] or all(r["message_id"] != theirs for r in sid_other)


def test_admin_list_summary_and_triage():
    db = SessionLocal()
    admin = _user(db, is_admin=True)
    person = _user(db)
    _, mid = _reply(db, person.id, text="A" * 600)
    aid, pid = admin.id, person.id
    db.close()

    c = _as(pid)
    c.post("/feedback", json={"rating": 1, "category": "problem", "message": "Search is slow", "page": "/dashboard"})
    c.post("/feedback", json={"rating": 5, "message": "Great"})
    c.put("/feedback/coach-reply", json={"message_id": mid, "helpful": False, "note": "Too generic"})

    # An ordinary user cannot read it.
    assert c.get("/admin/feedback").status_code == 403

    a = _as(aid)
    allrows = a.get("/admin/feedback").json()
    mine = [r for r in allrows if r["user_email"].startswith("fb") and r["status"] == "new"]
    assert any(r["message"] == "Search is slow" for r in mine)
    reply_row = next(r for r in allrows if r["kind"] == "coach_reply" and r["message"] == "Too generic")
    assert len(reply_row["reply_excerpt"]) == 400 and reply_row["helpful"] is False

    low = a.get("/admin/feedback?low=true").json()
    assert all((r["rating"] is not None and r["rating"] <= 2) or r["helpful"] is False for r in low)
    assert any(r["message"] == "Search is slow" for r in low) and not any(r["message"] == "Great" for r in low)
    assert all(r["kind"] == "coach_reply" for r in a.get("/admin/feedback?kind=coach_reply").json())

    s = a.get("/admin/feedback/summary").json()
    assert s["total"] >= 3 and s["thumbs_down"] >= 1 and s["avg_rating"] is not None

    fid = next(r["id"] for r in allrows if r["message"] == "Search is slow")
    assert a.post(f"/admin/feedback/{fid}/status?status=reviewed").status_code == 200
    assert a.post(f"/admin/feedback/{fid}/status?status=bogus").status_code == 422
    assert a.post("/admin/feedback/99999999/status?status=reviewed").status_code == 404
    assert next(r for r in a.get("/admin/feedback?status=reviewed").json() if r["id"] == fid)["status"] == "reviewed"
