import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal, get_db
from app.main import app
from app.security import get_current_user
from app.services import program, syllabus

ROADMAP = {
    "title": "Security Architect: zero to hired", "overview": "o", "role_summary": "r", "honest_note": "h",
    "titles": ["Security Analyst", "Security Engineer"],
    "foundations": {"name": "Security foundations", "goal": "g", "topic": "security basics", "skills": ["CIA triad"], "weeks": 4},
    "core": {"name": "Core security", "goal": "g", "topic": "network and cloud security", "skills": ["IAM"], "weeks": 6},
    "advanced": {"name": "Architecture", "goal": "g", "topic": "security architecture", "skills": ["Zero trust"], "weeks": 6},
    "projects": [{"title": "Threat model", "build": "b", "deliverable": "d"}, {"title": "Reference design", "build": "b", "deliverable": "d"}],
    "certs": [{"name": "Security+", "why": "w"}],
}


def _course(n=3):
    return {"title": "C", "overview": "", "outcomes": [], "prerequisites": [], "total_hours": 1, "modules": [
        {"id": f"m{i}", "title": f"Module {i}", "summary": "", "objectives": ["a", "b"], "lessons": [], "hands_on": "", "checkpoint": "", "minutes": 60}
        for i in range(1, n + 1)]}


def test_roadmap_has_three_learning_phases_then_projects_certs_and_job_ready():
    d = program.parse(json.dumps(ROADMAP), "Security Architect")
    assert [p["kind"] for p in d["phases"]] == ["foundations", "core", "advanced", "projects", "certs", "job_ready"]
    assert d["phases"][-1]["items"][1]["text"].count("Security Analyst") == 1
    assert d["titles"] == ["Security Analyst", "Security Engineer"]


def test_roadmap_without_certs_or_with_a_missing_phase():
    no_certs = dict(ROADMAP, certs=[])
    assert "certs" not in [p["kind"] for p in program.parse(json.dumps(no_certs), "x")["phases"]]
    broken = {k: v for k, v in ROADMAP.items() if k != "core"}
    with pytest.raises(ValueError):
        program.parse(json.dumps(broken), "x")


def _states(courses=None, state=None):
    d = program.parse(json.dumps(ROADMAP), "Security Architect")
    return d, program.phase_states(d, state or {}, courses or {})


def test_later_phases_are_locked_until_the_earlier_ones_are_done():
    _, ph = _states()
    assert [p["status"] for p in ph] == ["current", "locked", "locked", "locked", "locked", "locked"]
    done_first = {"p1": {"id": 1, "total": 3, "done": 3, "modules": []}}
    _, ph = _states(done_first)
    assert [p["status"] for p in ph][:3] == ["done", "current", "locked"]
    both = dict(done_first, p2={"id": 2, "total": 2, "done": 2, "modules": []})
    _, ph = _states(both)
    kinds = {p["kind"]: p["status"] for p in ph}
    assert kinds["advanced"] == "current"
    assert kinds["projects"] == "open" and kinds["job_ready"] == "open", "applying can start once core is done"


def test_next_step_and_week_plan_follow_the_hours_available():
    mods = [{"id": f"m{i}", "title": f"Module {i}", "minutes": 60, "done": i == 1} for i in range(1, 6)]
    courses = {"p1": {"id": 7, "total": 5, "done": 1, "modules": mods}}
    d, ph = _states(courses)
    step = program.next_step(ph, courses)
    assert step["kind"] == "module" and step["module_id"] == "m2" and step["course_id"] == 7
    plan = program.week_plan(ph, courses, 2)
    assert [x["module_id"] for x in plan["lessons"]] == ["m2", "m3"] and plan["minutes"] == 120
    assert program.next_step(program.phase_states(d, {}, {}), {})["kind"] == "build_phase"
    assert program.weeks_left(ph, courses, 4) == 1 + 6 + 6, "4 built hours at 4/wk is 1 week; unbuilt phases use their estimate"


def test_progress_ignores_optional_certs():
    d = program.parse(json.dumps(ROADMAP), "x")
    courses = {p: {"id": i, "total": 2, "done": 2, "modules": []} for i, p in enumerate(("p1", "p2", "p3"))}
    state = {"projects": {"0": {"done": True}, "1": {"done": True}}, "checklist": {i["id"]: True for i in d["phases"][-1]["items"]}}
    ph = program.phase_states(d, state, courses)
    assert program.overall_progress(ph) == 100 and all(p["status"] == "done" for p in ph if not p.get("optional"))


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"pg-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", full_name="Em",
                       resume_text="IT auditor for ten years.", subscription_tier="pro")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    yield db, user, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def _create(c, role="Security Architect"):
    with patch("app.services.program.build", return_value=program.parse(json.dumps(ROADMAP), role)) as b:
        r = c.post("/career-programs", json={"target_role": role, "hours_per_week": 5, "background": "IT audit"})
    return r, b


def test_create_program_passes_background_and_is_idempotent_per_role(ctx):
    _, _, c = ctx
    r, b = _create(c)
    assert r.status_code == 201 and r.json()["next_step"]["kind"] == "build_phase"
    assert b.call_args.args[1:3] == (5, "IT audit")
    r2, b2 = _create(c)
    assert r2.json()["id"] == r.json()["id"] and not b2.called, "same role returns the saved program, free"


def test_starting_a_phase_builds_its_course_from_zero_and_unlocks_in_order(ctx):
    _, _, c = ctx
    pid = _create(c)[0].json()["id"]
    assert c.post(f"/career-programs/{pid}/phases/p2/course").status_code == 400, "core is locked until foundations are done"
    with patch("app.services.syllabus.build", return_value=_course()) as sb:
        r = c.post(f"/career-programs/{pid}/phases/p1/course")
    assert r.status_code == 200
    assert "ONLY to choose relatable analogies" in sb.call_args.args[3] and "no experience" in sb.call_args.args[3]
    body = r.json()
    assert body["next_step"]["kind"] == "module" and body["next_step"]["module_id"] == "m1"
    assert body["phases"][0]["total"] == 3 and body["phases"][0]["modules"][0]["title"] == "Module 1"
    with patch("app.services.syllabus.build") as again:
        c.post(f"/career-programs/{pid}/phases/p1/course")
    assert not again.called, "the course is only built once"


def test_projects_certs_checklist_and_search_status_are_saved(ctx):
    _, _, c = ctx
    pid = _create(c)[0].json()["id"]
    r = c.put(f"/career-programs/{pid}/projects/0", json={"done": True, "url": "https://github.com/x/y", "note": "n"})
    p = [x for x in r.json()["phases"] if x["kind"] == "projects"][0]
    assert p["done"] == 1 and p["items"][0]["url"] == "https://github.com/x/y"
    assert c.put(f"/career-programs/{pid}/projects/9", json={"done": True}).status_code == 404
    r = c.put(f"/career-programs/{pid}/certs/0", json={"status": "studying"})
    assert [x for x in r.json()["phases"] if x["kind"] == "certs"][0]["items"][0]["status"] == "studying"
    r = c.put(f"/career-programs/{pid}/checklist/resume", json={"done": True})
    assert [x for x in r.json()["phases"] if x["kind"] == "job_ready"][0]["done"] == 1
    assert c.put(f"/career-programs/{pid}/checklist/nope", json={"done": True}).status_code == 404
    r = c.patch(f"/career-programs/{pid}", json={"status": "interviewing", "hours_per_week": 8})
    assert r.json()["status"] == "interviewing" and r.json()["hours_per_week"] == 8
    assert c.patch(f"/career-programs/{pid}", json={"status": "bogus"}).status_code == 422


def test_other_people_cannot_see_a_program(ctx):
    db, user, c = ctx
    pid = _create(c)[0].json()["id"]
    other = models.User(email=f"o-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", full_name="O")
    db.add(other); db.commit(); db.refresh(other)
    app.dependency_overrides[get_current_user] = lambda: other
    assert c.get(f"/career-programs/{pid}").status_code == 404
    assert c.delete(f"/career-programs/{pid}").status_code == 404


def test_test_out_brief_checks_instead_of_teaching_and_normal_brief_is_unchanged():
    course = _course()
    normal = syllabus.brief(course, "m1")
    test = syllabus.brief(course, "m1", test_out=True)
    assert "HOW TO TEACH IT" in normal and "TEST-OUT" not in normal
    assert "TEST-OUT" in test and "Do not teach yet" in test and "ONLY when the answer is correct" in test
    assert "HOW TO TEACH IT" not in test


def test_long_text_is_cut_at_a_word_or_sentence_not_mid_word():
    from app.services import program, syllabus
    text = ("A Security Architect designs the security blueprint of systems. "
            "Employers expect you to translate business risk into defensible technical designs and architecture documentation.")
    for line in (program._line, syllabus._line):
        assert line(text, 500) == text
        cut = line(text, 100)
        assert cut.endswith("systems.")                      # whole sentence
        cut = line("SABSA framework concepts and enterprise architecture layers", 40)
        assert cut.endswith("…") and cut[:-1] in "SABSA framework concepts and enterprise architecture layers"
        assert not cut[:-1].endswith(("enterpr", "archite"))  # no half words
