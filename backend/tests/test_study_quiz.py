"""Warm-up quiz on saved study notes: opt-in only, same notes all session,
result captured, role-plays untouched."""
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal, get_db
from app.main import app
from app.security import get_current_user
from app.services import career_coach as cc
from app.services import study_quiz

NOTE_A = "Threat modeling: STRIDE covers spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege."
NOTE_B = "Least privilege means giving an account only the access its task needs and removing it afterwards."


def _setup():
    db = SessionLocal()
    u = models.User(email=f"q{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", resume_text="Security engineer.")
    db.add(u); db.commit(); db.refresh(u)
    f = models.StudyFolder(user_id=u.id, name="Security")
    db.add(f); db.commit(); db.refresh(f)
    db.add_all([models.StudyNote(user_id=u.id, folder_id=f.id, title="STRIDE", content=NOTE_A),
                models.StudyNote(user_id=u.id, folder_id=None, title="Least privilege", content=NOTE_B),
                models.StudyNote(user_id=u.id, folder_id=f.id, title="tiny", content="short")])
    db.commit()
    uid, fid = u.id, f.id
    db.close()
    from fastapi import Depends

    def _u(db=Depends(get_db)):
        return db.get(models.User, uid)
    app.dependency_overrides[get_current_user] = _u
    return TestClient(app), uid, fid


def _resp(text):
    r = MagicMock(); r.content = [MagicMock(text=text)]; return r


def test_pick_by_folder_all_and_skips_tiny_notes():
    _, uid, fid = _setup()
    db = SessionLocal()
    folder = study_quiz.pick(db, uid, fid, False)
    assert [n.title for n in folder] == ["STRIDE"]
    assert {n.title for n in study_quiz.pick(db, uid, None, True)} == {"STRIDE", "Least privilege"}
    assert study_quiz.pick(db, uid, None, False) == []
    db.close()


def test_extract_result_hides_marker_and_validates():
    assert study_quiz.extract_result("Warm-up: 2 of 3. [[quiz:2/3]] On to goal one.") == ("Warm-up: 2 of 3. On to goal one.", "2/3")
    assert study_quiz.extract_result("x [[quiz:5/3]]")[1] == ""
    assert study_quiz.extract_result("no marker") == ("no marker", "")


def test_nothing_is_sent_unless_the_person_asks():
    client, uid, fid = _setup()
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: T\n---\nHi")) as m:
        r = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Security Engineer"})
    assert r.status_code == 200
    sent = m.call_args.kwargs["messages"][0]["content"]
    assert "STRIDE" not in sent and "WARM-UP QUIZ" not in sent
    assert r.json()["session"]["quizzed"] is False


def test_quiz_session_sends_picked_notes_start_and_replies_then_stops_after_result():
    client, uid, fid = _setup()
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: T\n---\nLet's warm up. Q1?")) as m:
        r = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Security Engineer", "quiz_folder_id": fid})
    assert r.status_code == 200, r.text
    sent = m.call_args.kwargs["messages"][0]["content"]
    assert "WARM-UP QUIZ REQUESTED" in sent and "STRIDE" in sent and "Least privilege" not in sent
    body = r.json()
    assert body["session"]["quizzed"] is True
    sid = body["session"]["id"]
    with patch.object(cc.client.messages, "create", return_value=_resp("Right. Q2?")) as m:
        client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "spoofing"})
    assert "WARM-UP QUIZ IN PROGRESS" in m.call_args.kwargs["system"] and "STRIDE" in m.call_args.kwargs["system"]
    with patch.object(cc.client.messages, "create", return_value=_resp("Warm-up: 2 of 3. [[quiz:2/3]] Now goal one.")) as m:
        r = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "last answer"})
    assert r.json()["quiz_result"] == "2/3" and "[[" not in r.json()["content"]
    with patch.object(cc.client.messages, "create", return_value=_resp("Goal one.")) as m:
        client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "ok"})
    assert "WARM-UP QUIZ" not in m.call_args.kwargs["system"]


def test_role_play_ignores_quiz_request():
    client, uid, fid = _setup()
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: T\n---\nTell me about you.")) as m:
        r = client.post("/career-coach/sessions", json={"session_type": "interview", "target_role": "Security Engineer", "quiz_all": True})
    assert "STRIDE" not in m.call_args.kwargs["messages"][0]["content"]
    assert r.json()["session"]["quizzed"] is False


def test_quiz_with_no_usable_notes_falls_back_to_a_normal_session():
    client, uid, fid = _setup()
    db = SessionLocal()
    empty = models.StudyFolder(user_id=uid, name="Empty"); db.add(empty); db.commit(); eid = empty.id; db.close()
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: T\n---\nHi")) as m:
        r = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Security Engineer", "quiz_folder_id": eid})
    assert r.status_code == 200 and "WARM-UP QUIZ" not in m.call_args.kwargs["messages"][0]["content"]
    assert r.json()["session"]["quizzed"] is False


def test_quiz_options_counts_only_usable_notes_without_text():
    client, uid, fid = _setup()
    body = client.get("/career-coach/study/quiz-options").json()
    assert body["all"] == 2 and body["folders"] == [{"id": fid, "name": "Security", "count": 1}]
    assert "STRIDE" not in str(body)
