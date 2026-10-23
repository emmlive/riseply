"""Autofill profile: validation, extraction parsing, ownership and metering."""
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main
from app.main import app as fastapp
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import autofill_profile as svc, admin_stats, usage

client = TestClient(fastapp)


@pytest.fixture()
def db():
    s = SessionLocal(); yield s; s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    fastapp.dependency_overrides.clear()


def _user(db, resume="Analyst at Acme 2019-2024. BS Accounting."):
    u = models.User(email=f"af{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T", resume_text=resume)
    db.add(u); db.commit(); db.refresh(u)
    fastapp.dependency_overrides[get_current_user] = lambda: u
    return u


def test_clean_drops_bad_values_and_never_defaults_sensitive_answers():
    d = svc.clean({"work": [{"company": "A", "title": "B", "current": 1, "evil": "x"}, {"company": "", "title": ""}, "junk"],
                   "answers": {"work_authorized_us": "maybe", "needs_sponsorship": "NO", "salary_expectation": "120k"},
                   "eeo": {"gender": "Banana", "veteran": "No"}, "skills": ["SQL", "sql", " ", "Python"],
                   "saved_answers": [{"question": "Why us?", "answer": "Because."}, {"question": "x", "answer": "y"}]})
    assert len(d["work"]) == 1 and d["work"][0]["current"] is True and "evil" not in d["work"][0]
    assert d["answers"]["work_authorized_us"] == "" and d["answers"]["needs_sponsorship"] == "no"
    assert d["eeo"]["gender"] == "" and d["eeo"]["veteran"] == "No" and d["eeo"]["race"] == ""
    assert d["skills"] == ["SQL", "Python"] and len(d["saved_answers"]) == 1
    e = svc.empty()
    assert all(v == "" for v in e["answers"].values()) and all(v == "" for v in e["eeo"].values())


def test_limits_applied():
    d = svc.clean({"work": [{"company": f"C{i}", "title": "t"} for i in range(40)], "skills": [f"s{i}" for i in range(80)]})
    assert len(d["work"]) == svc.MAX_WORK and len(d["skills"]) == svc.MAX_SKILLS


def test_parse_extraction_and_rejects_empty():
    ok = svc.parse_extraction('```json\n{"work":[{"company":"Acme","title":"Analyst","start":"2019","end":"2024"}],"education":[{"school":"MSU"}],"skills":["SQL"]}\n```')
    assert ok["work"][0]["company"] == "Acme" and set(ok) == {"work", "education", "skills"}
    with pytest.raises(ValueError):
        svc.parse_extraction('{"work":[],"education":[],"skills":[]}')
    with pytest.raises(ValueError):
        svc.parse_extraction("no json")


def test_roundtrip_and_isolation(db):
    u = _user(db)
    assert client.get("/autofill-profile").json()["profile"]["work"] == []
    r = client.put("/autofill-profile", json={"profile": {"answers": {"work_authorized_us": "yes"}, "saved_answers": [{"question": "Notice period?", "answer": "Two weeks"}]}})
    assert r.json()["profile"]["answers"]["work_authorized_us"] == "yes"
    _user(db)
    assert client.get("/autofill-profile").json()["profile"]["answers"]["work_authorized_us"] == ""


def test_from_resume_keeps_answers_and_refunds_on_failure(db):
    _user(db)
    client.put("/autofill-profile", json={"profile": {"answers": {"needs_sponsorship": "no"}}})
    good = {"work": [{"company": "Acme", "title": "Analyst"}], "education": [], "skills": ["SQL"]}
    with patch("app.routers.autofill_profile.svc.extract", return_value=good):
        r = client.post("/autofill-profile/from-resume").json()["profile"]
    assert r["work"][0]["company"] == "Acme" and r["answers"]["needs_sponsorship"] == "no"
    with patch("app.routers.autofill_profile.svc.extract", side_effect=RuntimeError("x")):
        assert client.post("/autofill-profile/from-resume").status_code == 502


def test_from_resume_needs_resume(db):
    _user(db, resume="")
    assert client.post("/autofill-profile/from-resume").status_code == 400


def test_action_has_limits_and_cost():
    assert "autofill_profile" in usage.FREE_LIMITS and "autofill_profile" in usage.PRO_LIMITS
    assert "autofill_profile" in admin_stats.ESTIMATED_COST_PER_ACTION


def test_address_new_answers_and_hispanic_are_kept_and_validated():
    d = svc.clean({"contact": {"address_line1": " 1 Main St ", "city": "Plainfield", "state": "IL", "postal_code": "60585",
                               "country": "United States", "phone_type": "Pager", "evil": "x"},
                   "answers": {"over_18": "yes", "government_official": "no", "related_to_official": "maybe",
                               "referral_source": "Indeed"},
                   "eeo": {"hispanic": "No"}})
    assert d["contact"]["address_line1"] == "1 Main St" and d["contact"]["postal_code"] == "60585"
    assert d["contact"]["phone_type"] == "" and "evil" not in d["contact"]
    assert d["answers"]["over_18"] == "yes" and d["answers"]["related_to_official"] == ""
    assert d["answers"]["referral_source"] == "Indeed" and d["eeo"]["hispanic"] == "No"
    e = svc.empty()
    assert e["contact"]["city"] == "" and e["answers"]["previously_employed"] == "" and e["eeo"]["hispanic"] == ""
