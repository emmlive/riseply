"""Questions Autofill couldn't answer: recorded, answerable once, counted across people."""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app.main import app as fastapp
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import unanswered

client = TestClient(fastapp)


@pytest.fixture()
def db():
    s = SessionLocal(); yield s; s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    fastapp.dependency_overrides.clear()


def _user(db):
    u = models.User(email=f"uq{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T", resume_text="Analyst")
    db.add(u); db.commit(); db.refresh(u)
    fastapp.dependency_overrides[get_current_user] = lambda: u
    return u


def test_usable_drops_short_personal_and_link_text():
    assert unanswered.usable("Are you willing to work weekends?")
    assert not unanswered.usable("Name")
    assert not unanswered.usable("Email me at jane@example.com about it")
    assert not unanswered.usable("Call 312 555 0100 for details please")
    assert not unanswered.usable("See https://example.com/policy for the policy")


def test_log_dedupes_counts_and_ignores_junk(db):
    u = _user(db)
    r = client.post("/extension/unanswered", json={"host": "Careers-X.iCIMS.com", "questions": [
        "Are you willing to work weekends?", "are you willing to work weekends", "ok", "x@y.com is my email"]})
    assert r.status_code == 200 and r.json()["recorded"] == 1
    r = client.post("/extension/unanswered", json={"host": "careers-x.icims.com", "questions": ["Are you willing to work weekends?"]})
    assert r.json()["recorded"] == 0
    rows = db.query(models.UnansweredQuestion).filter_by(user_id=u.id).all()
    assert len(rows) == 1 and rows[0].times_seen == 2 and rows[0].host == "careers-x.icims.com"
    assert client.post("/extension/unanswered", json={"questions": "nope"}).status_code == 422


def test_answering_saves_an_autofill_answer_and_clears_the_question(db):
    _user(db)
    client.post("/extension/unanswered", json={"host": "a.com", "questions": ["Why do you want to work here?"]})
    qs = client.get("/autofill-profile/unanswered").json()["questions"]
    assert len(qs) == 1
    assert client.post(f"/autofill-profile/unanswered/{qs[0]['id']}/answer", json={"answer": " "}).status_code == 422
    r = client.post(f"/autofill-profile/unanswered/{qs[0]['id']}/answer", json={"answer": "I like the mission."})
    assert r.status_code == 200
    assert r.json()["profile"]["saved_answers"] == [{"question": "Why do you want to work here?", "answer": "I like the mission."}]
    assert client.get("/autofill-profile/unanswered").json()["questions"] == []
    # asked again later: it comes back, and answering replaces the saved answer instead of duplicating it
    client.post("/extension/unanswered", json={"host": "a.com", "questions": ["Why do you want to work here?"]})
    q2 = client.get("/autofill-profile/unanswered").json()["questions"][0]
    r = client.post(f"/autofill-profile/unanswered/{q2['id']}/answer", json={"answer": "Updated."})
    assert [x["answer"] for x in r.json()["profile"]["saved_answers"]] == ["Updated."]


def test_dismiss_and_privacy(db):
    _user(db)
    client.post("/extension/unanswered", json={"host": "a.com", "questions": ["Do you have a valid driver license?"]})
    qid = client.get("/autofill-profile/unanswered").json()["questions"][0]["id"]
    other = _user(db)  # someone else cannot touch it
    assert client.post(f"/autofill-profile/unanswered/{qid}/dismiss").status_code == 404
    assert client.post(f"/autofill-profile/unanswered/{qid}/answer", json={"answer": "x"}).status_code == 404
    assert client.get("/autofill-profile/unanswered").json()["questions"] == []


def test_admin_summary_counts_people_without_names(db):
    from app.security import get_current_admin
    from app.routers import admin as admin_router
    q = "Will you now or in the future require visa sponsorship zz?"
    for _ in range(2):
        _user(db)
        client.post("/extension/unanswered", json={"host": "b.com", "questions": [q]})
    admin = models.User(email=f"ad{uuid.uuid4().hex[:6]}@x.com", hashed_password="x", full_name="A", is_admin=True, admin_role="super")
    db.add(admin); db.commit(); db.refresh(admin)
    fastapp.dependency_overrides[get_current_admin] = lambda: admin
    rows = client.get("/admin/unanswered-questions").json()
    hit = next(r for r in rows if r["question"] == q)
    assert hit["people"] == 2 and hit["times_seen"] == 2 and hit["sample_site"] == "b.com"
    assert set(hit) == {"question", "people", "times_seen", "sample_site", "last_seen"}
    fastapp.dependency_overrides.pop(get_current_admin, None)
