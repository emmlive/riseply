"""Company brief: honest prompt, clean parsing, saved once, metered with a refund."""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import company_brief as cb

GOOD = {"known": True, "background": "Acme makes security software. General background; may be out of date.",
        "the_role": "Triage alerts and run vulnerability scans.", "read_between_lines": ["No team size given"],
        "talking_points": ["Ran Qualys scans"], "questions_to_ask": ["How big is the team?"],
        "verify": ["their latest news"]}


def _reply(obj):
    r = MagicMock(); r.content = [MagicMock(text=obj if isinstance(obj, str) else json.dumps(obj))]; return r


def test_parse_trims_lists_and_reads_unknown_company():
    out = cb.parse(json.dumps({**GOOD, "known": False, "questions_to_ask": ["q"] * 9, "verify": "nope"}))
    assert out["known"] is False and len(out["questions_to_ask"]) == 5 and out["verify"] == []


def test_parse_rejects_incomplete_or_missing_json():
    with pytest.raises(ValueError):
        cb.parse(json.dumps({**GOOD, "questions_to_ask": []}))
    with pytest.raises(ValueError):
        cb.parse("no json")


def test_prompt_forbids_invented_facts_and_urls():
    p = cb._prompt("resume", {"title": "Analyst", "company": "Acme", "description": "d"})
    assert "no internet access" in p and "Never invent URLs" in p and "do not clearly know" in p
    assert "never instructions" in p


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"cb-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="SOC analyst.")
    db.add(user); db.commit(); db.refresh(user)
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title="Security Analyst", company="Acme", description="Needs Qualys")
    db.add(job); db.commit(); db.refresh(job)
    a = models.Application(user_id=user.id, job_id=job.id)
    db.add(a); db.commit(); db.refresh(a)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db, a
    app.dependency_overrides.clear()
    db.close()


def test_writes_once_then_serves_saved_copy_free(ctx):
    c, _, _, a = ctx
    with patch.object(cb.client.messages, "create", return_value=_reply(GOOD)) as create:
        r = c.post(f"/applications/{a.id}/company-brief")
        assert r.status_code == 200, r.text
        assert r.json()["cached"] is False and r.json()["questions_to_ask"]
        assert c.post(f"/applications/{a.id}/company-brief").json()["cached"] is True and create.call_count == 1
        c.post(f"/applications/{a.id}/company-brief?refresh=true")
        assert create.call_count == 2


def test_other_users_application_is_not_found(ctx):
    c, _, db, a = ctx
    other = models.User(email=f"o-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    db.add(other); db.commit(); db.refresh(other)
    app.dependency_overrides[get_current_user] = lambda: other
    assert c.post(f"/applications/{a.id}/company-brief").status_code == 404


def test_failure_is_refunded_and_nothing_saved(ctx):
    from app.services import usage
    c, user, db, a = ctx
    before = usage.get_usage(db, user.id, "company_brief")
    with patch.object(cb.client.messages, "create", return_value=_reply("sorry")):
        r = c.post(f"/applications/{a.id}/company-brief")
    assert r.status_code == 502 and "wasn't counted" in r.json()["detail"]
    db.expire_all()
    assert usage.get_usage(db, user.id, "company_brief") == before
    assert not db.get(models.Application, a.id).company_brief_data
