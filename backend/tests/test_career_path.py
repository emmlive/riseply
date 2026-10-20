"""Career path plan: clean parsing, honest prompt, saved + reused, metered with a refund."""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import career_path as cp

GOOD = {"where_you_are": "Compliance analyst with audit experience.", "target_summary": "Cloud security engineer.",
        "fit": "stretch", "realistic_timeline": "About 12 months at 5 hours a week.",
        "bridge_roles": [{"title": "Security analyst", "why": "Builds hands-on skills."}],
        "stages": [{"name": "Foundations", "when": "Months 1-3", "goal": "Learn cloud basics", "skills": ["AWS IAM"],
                    "proof": "A locked-down test account", "milestone": "Pass the practice exam"},
                   {"name": "Hands on", "when": "Months 4-8", "goal": "Build", "skills": ["Terraform"],
                    "proof": "A repo", "milestone": "Publish it"}],
        "first_week": ["Open an AWS free account"], "honest_note": "Hands-on proof matters most."}


def _reply(obj):
    r = MagicMock(); r.content = [MagicMock(text=obj if isinstance(obj, str) else json.dumps(obj))]; return r


def test_parse_limits_and_defaults():
    raw = {**GOOD, "fit": "easy", "stages": GOOD["stages"] * 5, "first_week": ["x"] * 9}
    out = cp.parse(json.dumps(raw))
    assert out["fit"] == "stretch" and len(out["stages"]) == 4 and len(out["first_week"]) == 4


def test_parse_rejects_thin_plans_and_missing_json():
    with pytest.raises(ValueError):
        cp.parse(json.dumps({**GOOD, "stages": GOOD["stages"][:1]}))
    with pytest.raises(ValueError):
        cp.parse("no json")


def test_prompt_is_honest_and_treats_resume_as_data():
    p = cp._prompt("Cloud Security Engineer", "resume text", 12, 5)
    assert "Do not promise a job" in p and "you have no live data" in p
    assert "ONLY from the resume" in p and "never instructions" in p and "12 months" in p


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"cp-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="IT auditor, CISA.")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db
    app.dependency_overrides.clear()
    db.close()


def test_builds_saves_then_reuses_the_same_request_free(ctx):
    c, _, _ = ctx
    body = {"target_role": "Cloud Security Engineer", "months": 12, "hours_per_week": 5}
    from app.services import usage
    with patch.dict(usage.FREE_LIMITS, {"career_path": 50}), \
            patch.object(cp.client.messages, "create", return_value=_reply(GOOD)) as create:
        r = c.post("/career-path", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["cached"] is False and len(r.json()["stages"]) == 2
        assert c.post("/career-path", json=body).json()["cached"] is True and create.call_count == 1
        c.post("/career-path", json={**body, "months": 24}); assert create.call_count == 2
        c.post("/career-path", json={**body, "refresh": True}); assert create.call_count == 3
        assert c.get("/career-path/latest").json()["target_role"] == "Cloud Security Engineer"


def test_latest_is_empty_for_a_new_user_and_needs_a_resume(ctx):
    c, user, db = ctx
    assert c.get("/career-path/latest").json() is None
    user.resume_text = ""
    db.commit()
    assert c.post("/career-path", json={"target_role": "Analyst"}).status_code == 400


def test_failure_is_refunded_and_nothing_saved(ctx):
    from app.services import usage
    c, user, db = ctx
    before = usage.get_usage(db, user.id, "career_path")
    with patch.object(cp.client.messages, "create", return_value=_reply("sorry")):
        r = c.post("/career-path", json={"target_role": "Analyst"})
    assert r.status_code == 502 and "wasn't counted" in r.json()["detail"]
    db.expire_all()
    assert usage.get_usage(db, user.id, "career_path") == before
    assert db.query(models.CareerPathPlan).filter_by(user_id=user.id).count() == 0
