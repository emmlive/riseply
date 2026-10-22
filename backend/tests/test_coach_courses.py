"""Career Coach courses: syllabus parsing, endpoints, module lessons, recaps."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import syllabus, usage

client = TestClient(app)
_n = [0]
CC = "app.routers.career_coach.career_coach_service"
BUILD = "app.routers.coach_courses.syllabus.build"
RECAP = "app.routers.coach_courses.syllabus.make_recap"


def _mods(n=4):
    return [{"title": f"Module {i}", "summary": "s", "objectives": ["Explain A", "Do B", "Spot C"],
             "lessons": ["x", "y"], "hands_on": "try it", "checkpoint": "answer it", "minutes": 40} for i in range(1, n + 1)]


def _syl(n=4):
    return syllabus.parse(json.dumps({"title": "Cloud Security Basics", "overview": "o", "outcomes": ["a"],
                                      "prerequisites": [], "total_hours": 0, "modules": _mods(n)}))


RECAP_OK = {"summary": "You covered A.", "key_points": ["A is x.", "B is y."], "terms": [{"term": "A", "meaning": "x"}],
            "example": "e", "practice": "p", "shaky": [], "next_up": "Module 2"}


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _user(db, resume="Support specialist"):
    _n[0] += 1
    u = models.User(email=f"course{_n[0]}@x.com", hashed_password="x", full_name="T", resume_text=resume)
    db.add(u); db.commit(); db.refresh(u)
    app.dependency_overrides[get_current_user] = lambda: u
    return u


def _course(role="Cloud Security Engineer"):
    with patch(BUILD, return_value=_syl()):
        return client.post("/career-coach/courses", json={"target_role": role, "topic": "", "skills": ["IAM"]})


def test_parse_assigns_ids_hours_and_rejects_thin():
    s = _syl(4)
    assert [m["id"] for m in s["modules"]] == ["m1", "m2", "m3", "m4"]
    assert s["total_hours"] == round(4 * 40 / 60, 1)
    with pytest.raises(ValueError):
        syllabus.parse(json.dumps({"title": "x", "modules": _mods(2)}))
    with pytest.raises(ValueError):
        syllabus.parse("nope")


def test_parse_drops_modules_without_objectives_and_caps_goals():
    mods = _mods(5)
    mods[0]["objectives"] = ["only one"]
    mods[1]["objectives"] = [f"goal {i}" for i in range(9)]
    s = syllabus.parse(json.dumps({"title": "T", "modules": mods}))
    assert len(s["modules"]) == 4 and len(s["modules"][0]["objectives"]) == 4


def test_brief_teaches_from_basics_and_names_position():
    s = _syl()
    b = syllabus.brief(s, "m2")
    assert "module 2 of 4" in b and "new to this subject" in b and "this module" in b
    assert syllabus.brief(s, "zz") == ""


def test_recap_parse_and_note():
    r = syllabus.parse_recap(json.dumps(RECAP_OK))
    title, text = syllabus.recap_note(_syl(), "m1", r)
    assert title.startswith("Module 1:") and "Key points" in text and "- A: x" in text
    with pytest.raises(ValueError):
        syllabus.parse_recap(json.dumps({"summary": "x", "key_points": ["one"]}))


def test_create_course_meters_reuses_and_refunds(db):
    u = _user(db)
    r = _course()
    assert r.status_code == 201 and len(r.json()["modules"]) == 4
    db.expire_all()
    assert usage.get_usage(db, u.id, "course") == 1
    again = _course()  # same role/topic: no second syllabus, no second charge
    assert again.json()["id"] == r.json()["id"]
    db.expire_all()
    assert usage.get_usage(db, u.id, "course") == 1
    with patch(BUILD, side_effect=RuntimeError("boom")):
        bad = client.post("/career-coach/courses", json={"target_role": "Other Role"})
    assert bad.status_code == 502
    db.expire_all()
    assert usage.get_usage(db, u.id, "course") == 1


def test_create_course_needs_resume(db):
    _user(db, resume="")
    assert _course().status_code == 400


def test_courses_are_private(db):
    _user(db)
    cid = _course().json()["id"]
    _user(db)
    assert client.get(f"/career-coach/courses/{cid}").status_code == 404
    assert client.delete(f"/career-coach/courses/{cid}").status_code == 404
    assert client.get("/career-coach/courses").json() == []


def _start_module(cid, mid="m1"):
    with patch(f"{CC}.start_session", return_value={"topic": "ignored", "opening_message": "Welcome to module one.", "goals": None}) as m:
        r = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Cloud Role", "course_id": cid, "module_id": mid})
    return r, m


def test_module_session_uses_objectives_as_plan_and_forces_upskill(db):
    _user(db)
    cid = _course().json()["id"]
    r, m = _start_module(cid)
    assert r.status_code == 200
    s = r.json()["session"]
    assert s["course_id"] == cid and s["module_id"] == "m1" and s["topic"] == "Module 1"
    assert s["lesson"]["goals"] == ["Explain A", "Do B", "Spot C"]
    assert m.call_args.args[0] == "upskill" and "COURSE MODULE" in m.call_args.kwargs["module"]


def test_module_session_unknown_module_is_404_and_not_charged(db):
    u = _user(db)
    cid = _course().json()["id"]
    r, _ = _start_module(cid, "m9")
    assert r.status_code == 404
    db.expire_all()
    assert usage.get_usage(db, u.id, "career_coach_message") == 0


def _msg(sid, text="my answer"):
    return client.post(f"/career-coach/sessions/{sid}/messages", json={"message": text})


def test_recap_arrives_when_all_objectives_covered_and_marks_module_done(db):
    _user(db)
    cid = _course().json()["id"]
    sid = _start_module(cid)[0].json()["session"]["id"]
    with patch(f"{CC}.reply", return_value="Good. [[covered:1]]"):
        r = _msg(sid)
    assert r.json()["recap"] is None and r.json()["lesson"]["covered"] == [1]
    with patch(f"{CC}.reply", return_value="Great. [[covered:2]] [[covered:3]] Module done."), patch(RECAP, return_value=RECAP_OK):
        r = _msg(sid)
    assert r.json()["recap"]["summary"] == "You covered A."
    course = client.get(f"/career-coach/courses/{cid}").json()
    assert course["done"] == 1 and course["modules"][0]["done"] and course["modules"][0]["recap_ready"]
    assert client.get("/career-coach/sessions").json()[0]["recap"]["key_points"]


def test_recap_failure_does_not_break_the_lesson(db):
    _user(db)
    cid = _course().json()["id"]
    sid = _start_module(cid)[0].json()["session"]["id"]
    with patch(f"{CC}.reply", return_value="All done [[covered:1]][[covered:2]][[covered:3]]"), patch(RECAP, side_effect=RuntimeError("x")):
        r = _msg(sid)
    assert r.status_code == 200 and r.json()["recap"] is None
    # ...and it can be rebuilt on request once there are enough exchanges.
    with patch(f"{CC}.reply", return_value="ok"):
        _msg(sid)
    with patch(RECAP, return_value=RECAP_OK):
        assert client.post(f"/career-coach/courses/sessions/{sid}/recap").json()["summary"] == "You covered A."


def test_save_recap_creates_course_folder_once_and_replaces_note(db):
    u = _user(db)
    cid = _course().json()["id"]
    sid = _start_module(cid)[0].json()["session"]["id"]
    assert client.post(f"/career-coach/courses/sessions/{sid}/save-recap").status_code == 404  # nothing yet
    with patch(f"{CC}.reply", return_value="[[covered:1]][[covered:2]][[covered:3]]"), patch(RECAP, return_value=RECAP_OK):
        _msg(sid)
    a = client.post(f"/career-coach/courses/sessions/{sid}/save-recap")
    b = client.post(f"/career-coach/courses/sessions/{sid}/save-recap")
    assert a.status_code == 201 and a.json()["id"] == b.json()["id"] and a.json()["source"] == "recap"
    folders = client.get("/career-coach/study/folders").json()
    assert [f["name"] for f in folders] == ["Course: Cloud Security Basics"] and folders[0]["note_count"] == 1


def test_complete_builds_missing_recap_and_marks_done(db):
    _user(db)
    cid = _course().json()["id"]
    sid = _start_module(cid)[0].json()["session"]["id"]
    with patch(f"{CC}.reply", return_value="Let's go on."):
        _msg(sid)
    with patch(f"{CC}.finish_session", return_value={"score": 7, "feedback": "ok"}), patch(RECAP, return_value=RECAP_OK):
        r = client.post(f"/career-coach/sessions/{sid}/complete")
    assert r.status_code == 200 and r.json()["recap"]["practice"] == "p"
    assert client.get(f"/career-coach/courses/{cid}").json()["done"] == 1


def test_delete_course_keeps_sessions(db):
    _user(db)
    cid = _course().json()["id"]
    _start_module(cid)
    assert client.delete(f"/career-coach/courses/{cid}").status_code == 204
    s = client.get("/career-coach/sessions").json()
    assert len(s) == 1 and s[0]["course_id"] is None
