"""Dashboard 'Do this next': derived from existing rows, most urgent first, no AI."""
import uuid
from datetime import datetime, timedelta

from app import models
from app.main import app as _app  # noqa: F401  (creates the tables)
from app.database import SessionLocal
from app.services import next_actions as na


def _user(db, resume="SOC analyst"):
    u = models.User(email=f"na-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text=resume)
    db.add(u); db.commit(); db.refresh(u); return u


def _app(db, user, status, days=0, **kw):
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title="Analyst", company="Acme", description="d")
    db.add(job); db.commit(); db.refresh(job)
    a = models.Application(user_id=user.id, job_id=job.id, status=status,
                           submitted_at=datetime.utcnow() - timedelta(days=days) if days else None, **kw)
    db.add(a); db.commit(); db.refresh(a); return a


def test_no_resume_means_one_clear_first_step():
    db = SessionLocal()
    out = na.build(db, _user(db, resume=""))
    assert [a["key"] for a in out] == ["add_resume"]
    db.close()


def test_new_user_is_pointed_at_skill_gaps():
    db = SessionLocal()
    assert [a["key"] for a in na.build(db, _user(db))] == ["first_search", "autofill_profile", "skill_gap"]
    db.close()


def test_orders_interview_prep_then_quiet_then_review_and_caps_at_four():
    db = SessionLocal()
    u = _user(db)
    _app(db, u, "pending_approval"); _app(db, u, "submitted", days=10)
    ia = _app(db, u, "interviewing", days=12)
    keys = [a["key"] for a in na.build(db, u)]
    assert keys[:4] == [f"prep-{ia.id}", "mock", "quiet", "review"] and len(keys) == 4
    db.add(models.InterviewPrep(application_id=ia.id, user_id=u.id, brief="B")); db.commit()
    assert [a["key"] for a in na.build(db, u)][:3] == ["mock", "quiet", "review"]
    db.close()


def test_ignores_fresh_archived_and_employer_applications():
    db = SessionLocal()
    u = _user(db)
    _app(db, u, "submitted", days=2)
    _app(db, u, "submitted", days=20, is_archived=True)
    assert [a["key"] for a in na.build(db, u)] == ["autofill_profile", "skill_gap"]
    db.close()


def test_endpoint_returns_the_list(client=None):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.security import get_current_user
    db = SessionLocal()
    u = _user(db)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        r = TestClient(app).get("/progress/next-actions")
        assert r.status_code == 200 and r.json()[0]["key"] == "first_search" and r.json()[0]["href"] and r.json()[0]["stage"] == "find"
    finally:
        app.dependency_overrides.clear(); db.close()


def test_every_suggestion_names_its_stage_and_finished_steps_drop_out():
    db = SessionLocal()
    u = _user(db)
    assert {a["stage"] for a in na.build(db, u)} <= {"get_ready", "find", "apply", "win", "grow"}
    u.used_welcome_search = True
    db.add(models.AutofillProfile(user_id=u.id, data="{}")); db.commit()
    assert [a["key"] for a in na.build(db, u)] == ["skill_gap"]
    db.close()


def test_exam_prep_is_offered_once_there_is_a_career_plan():
    db = SessionLocal()
    u = _user(db)
    u.used_welcome_search = True
    db.add(models.AutofillProfile(user_id=u.id, data="{}"))
    db.add(models.SkillGapReport(user_id=u.id, target_role="x")); db.add(models.CareerPathPlan(user_id=u.id, target_role="x")); db.commit()
    assert [a["key"] for a in na.build(db, u)] == ["exam_prep"]
    db.add(models.ExamPrep(user_id=u.id, exam_name="CISA")); db.commit()
    assert na.build(db, u) == []
    db.close()


def test_journey_marks_done_current_and_todo():
    db = SessionLocal()
    u = _user(db)
    j = na.journey(db, u)
    assert [s["key"] for s in j["stages"]] == ["get_ready", "find", "apply", "win", "grow"]
    assert j["current"] == "find" and j["stages"][1]["state"] == "current"   # first suggestion is the first search
    assert j["stages"][0]["stat"] == "Save your form answers" and j["stages"][0]["state"] == "todo"
    _app(db, u, "submitted", days=2); ia = _app(db, u, "interviewing", days=3)
    u.used_welcome_search = True
    db.add(models.AutofillProfile(user_id=u.id, data="{}")); db.commit()
    j = na.journey(db, u)
    by = {s["key"]: s for s in j["stages"]}
    assert by["get_ready"]["state"] == "done" and by["find"]["state"] == "done" and by["apply"]["state"] == "done"
    assert by["apply"]["stat"] == "2 sent" and by["win"]["stat"] == "1 interviewing"
    assert j["current"] == "win" and by["win"]["state"] == "current"   # interview prep is the most urgent thing
    db.close()


def test_journey_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.security import get_current_user
    db = SessionLocal()
    u = _user(db)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        r = TestClient(app).get("/progress/journey")
        assert r.status_code == 200 and len(r.json()["stages"]) == 5 and r.json()["current"] in {s["key"] for s in r.json()["stages"]}
    finally:
        app.dependency_overrides.clear(); db.close()
