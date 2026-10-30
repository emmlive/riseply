"""A resume with what the person learned in a Career Coach course: only finished
modules, worded as training, the original text untouched, claims the modules
don't support dropped, metered with a refund on failure."""
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import coach_resume as cr, usage

BASE = """JANE DOE
jane@example.com

SUMMARY
IT auditor with SOX and access control testing experience.

EXPERIENCE
Federal Bank, IT Auditor (2019 - Present)
- Tested access controls on SWIFT systems.
- Wrote 40 audit reports.

SKILLS
SOX, Access reviews, Audit planning

EDUCATION
M.S. Cybersecurity, Missouri State University
"""

MODS = [
    {"id": "m1", "title": "Trust boundaries and security zones", "objectives": ["Explain trust boundaries", "Draw a two-zone diagram"],
     "hands_on": "Draw a two-zone diagram for a loan app", "summary": "", "lessons": [], "checkpoint": "", "minutes": 45},
    {"id": "m2", "title": "Threat modeling basics", "objectives": ["Identify threats with STRIDE", "Rank risks"],
     "hands_on": "", "summary": "", "lessons": [], "checkpoint": "", "minutes": 45},
    {"id": "m3", "title": "Zero trust networks", "objectives": ["Describe zero trust", "Compare it to a perimeter model"],
     "hands_on": "", "summary": "", "lessons": [], "checkpoint": "", "minutes": 45},
]


def items(picked=("m1", "m2"), done=("m1", "m2")):
    return cr.evidence(MODS, set(done), list(picked), {"m1": {"terms": [{"term": "Trust boundary", "meaning": "x"}]}})


def test_evidence_only_finished_and_chosen_modules():
    assert [i["id"] for i in items(picked=("m1", "m2", "m3"), done=("m1", "m3"))] == ["m1", "m3"], "m2 is not finished"
    assert [i["id"] for i in items(picked=("m1",), done=("m1", "m2"))] == ["m1"], "m2 was not chosen"
    assert items(picked=("m3",), done=("m1",)) == []
    assert items()[0]["terms"] == ["Trust boundary"]


def test_training_lines_drop_work_claims_and_invented_numbers():
    it = items()
    got = cr.clean_training([
        "Completed training in trust boundaries and security zone design",
        "Led a team that cut risk by 40%",                              # work claim + number
        "Practiced threat modeling with STRIDE across 12 systems",      # number the modules never gave
        "Certified in threat modeling",                                  # certification
        "- Studied how to rank risks in a threat model",
        "too short",
    ], it)
    assert got == ["Completed training in trust boundaries and security zone design",
                   "Studied how to rank risks in a threat model"]


def test_skills_must_come_from_the_modules_and_not_repeat_the_resume():
    it = items()
    got = cr.clean_skills(["Threat modeling", "Trust boundaries", "Kubernetes", "STRIDE", "SOX", "Security zones design review leadership"], it, BASE)
    assert got == ["Threat modeling", "Trust boundaries", "STRIDE"]   # Kubernetes was never taught; SOX is already there; too long


def test_assemble_keeps_every_original_line_and_adds_the_two_pieces():
    out = cr.assemble(BASE, ["Completed training in zones."], ["Threat modeling", "STRIDE"])
    original = [l for l in BASE.split("\n") if l.strip()]
    kept = [l for l in out.split("\n") if l.strip()]
    for line in original:
        assert line in kept, line
    assert "Recently trained in: Threat modeling, STRIDE" in out
    assert out.index("SKILLS") < out.index("Recently trained in") < out.index("EDUCATION")
    assert out.index("PROFESSIONAL DEVELOPMENT") < out.index("EDUCATION")
    assert out.index("EXPERIENCE") < out.index("PROFESSIONAL DEVELOPMENT")
    assert "- Completed training in zones." in out


def test_assemble_without_skills_or_education_headings():
    out = cr.assemble("Jane Doe\nIT auditor\n\nExperience\nBank, auditor", ["Completed training in zones."], ["STRIDE"])
    assert out.rstrip().endswith("Skills practiced: STRIDE") or "Recently trained in: STRIDE" in out
    assert "Professional Development" in out and out.index("Experience") < out.index("Professional Development")


def test_assemble_adds_to_an_existing_section_instead_of_a_second_one():
    first = cr.assemble(BASE, ["Completed training in zones."], [])
    second = cr.assemble(first, ["Studied threat modeling."], [])
    assert second.count("PROFESSIONAL DEVELOPMENT") == 1 and "Studied threat modeling." in second


def test_fallback_wording_when_the_model_fails():
    with patch.object(cr.client.messages, "create", side_effect=RuntimeError("down")):
        got = cr.generate("Security Architect", "Course", items(), BASE)
    assert got["skills"] == [] and len(got["training"]) == 2
    assert got["training"][0].startswith("Completed training module: Trust boundaries and security zones")


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"cr-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text=BASE)
    db.add(user); db.commit(); db.refresh(user)
    db.add(models.Resume(user_id=user.id, label="Main resume", resume_text=BASE, is_default=True)); db.commit()
    course = models.CoachCourse(user_id=user.id, target_role="Security Architect", title="Security Architecture",
                                data=json.dumps({"title": "Security Architecture", "modules": MODS}), done=json.dumps(["m1", "m2"]))
    db.add(course); db.commit(); db.refresh(course)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, course, db
    app.dependency_overrides.clear()
    db.close()


GOOD = json.dumps({"training": ["Completed training in trust boundaries and security zone design", "Studied threat modeling with STRIDE"],
                   "skills": ["Threat modeling", "Zero trust"]})


class _Resp:
    def __init__(self, text): self.content = [type("B", (), {"text": text})()]


def test_endpoint_builds_a_copy_and_counts_once(ctx):
    c, user, course, db = ctx
    before = usage.get_usage(db, user.id, "learned_resume")
    with patch.object(cr.client.messages, "create", return_value=_Resp(GOOD)):
        r = c.post(f"/career-coach/courses/{course.id}/learned-resume", json={"module_ids": ["m1", "m2", "m3"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["label"] == "Main resume + Security Architect training" and j["modules"] == ["Trust boundaries and security zones", "Threat modeling basics"]
    assert "Zero trust" not in j["skills"], "m3 was never finished, so its skill is not allowed"
    assert j["skills"] == ["Threat modeling"] and "Wrote 40 audit reports." in j["resume_text"]
    assert usage.get_usage(db, user.id, "learned_resume") == before + 1
    assert db.query(models.Resume).filter_by(user_id=user.id).count() == 1, "nothing is saved until the person saves it"


def test_unfinished_modules_and_empty_resume_are_refused(ctx):
    c, user, course, db = ctx
    before = usage.get_usage(db, user.id, "learned_resume")
    assert c.post(f"/career-coach/courses/{course.id}/learned-resume", json={"module_ids": ["m3"]}).status_code == 422
    user.resume_text = ""
    db.query(models.Resume).filter_by(user_id=user.id).delete(); db.commit()
    assert c.post(f"/career-coach/courses/{course.id}/learned-resume", json={"module_ids": ["m1"]}).status_code == 422
    assert usage.get_usage(db, user.id, "learned_resume") == before


def test_someone_elses_course_is_not_found(ctx):
    c, user, course, db = ctx
    other = models.User(email=f"o-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text=BASE)
    db.add(other); db.commit(); db.refresh(other)
    app.dependency_overrides[get_current_user] = lambda: other
    assert c.post(f"/career-coach/courses/{course.id}/learned-resume", json={"module_ids": ["m1"]}).status_code == 404
