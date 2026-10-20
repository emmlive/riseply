"""Networking drafts: honest prompt, clean parsing, saved once, metered with a refund."""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import networking as nw

GOOD = {"connect": "Hi Sam, I'm a SOC analyst applying for the Security Analyst role at Acme.",
        "recruiter": "Hi Sam,\nI applied for the Security Analyst role.", "referral": "Hi [Name],\nCould you point me to the right person?",
        "follow_up": "Hi Sam,\nFollowing up on my application.", "thank_you": "Thanks for your time on [date].",
        "tip": "Send the connect note first."}


def _reply(obj):
    r = MagicMock(); r.content = [MagicMock(text=obj if isinstance(obj, str) else json.dumps(obj))]; return r


def test_parse_keeps_five_drafts_in_order_and_clips_the_connect_note():
    out = nw.parse(json.dumps({**GOOD, "connect": "word " * 200}))
    assert [d["kind"] for d in out["drafts"]] == ["connect", "recruiter", "referral", "follow_up", "thank_you"]
    assert len(out["drafts"][0]["text"]) <= 281


def test_parse_drops_empty_drafts_but_needs_at_least_three():
    out = nw.parse(json.dumps({**GOOD, "referral": "", "thank_you": ""}))
    assert len(out["drafts"]) == 3
    with pytest.raises(ValueError):
        nw.parse(json.dumps({"connect": "x", "tip": "y"}))
    with pytest.raises(ValueError):
        nw.parse("no json")


def test_prompt_forbids_invented_connections_and_names_the_contact():
    p = nw._prompt("resume", {"title": "Analyst", "company": "Acme", "description": "d"}, "Sam Lee", "Recruiter")
    assert "Never invent a mutual connection" in p and "bracket placeholder" in p
    assert "Sam Lee (Recruiter)" in p and "never instructions" in p


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"nw-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="SOC analyst, Splunk.")
    db.add(user); db.commit(); db.refresh(user)
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title="Security Analyst", company="Acme", description="Needs Qualys")
    db.add(job); db.commit(); db.refresh(job)
    application = models.Application(user_id=user.id, job_id=job.id)
    db.add(application); db.commit(); db.refresh(application)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db, application
    app.dependency_overrides.clear()
    db.close()


def test_writes_once_then_serves_the_saved_copy_free(ctx):
    c, _, _, a = ctx
    with patch.object(nw.client.messages, "create", return_value=_reply(GOOD)) as create:
        r = c.post(f"/applications/{a.id}/networking")
        assert r.status_code == 200, r.text
        assert len(r.json()["drafts"]) == 5 and r.json()["cached"] is False
        assert c.post(f"/applications/{a.id}/networking").json()["cached"] is True and create.call_count == 1
        c.post(f"/applications/{a.id}/networking", json={"refresh": True})
        assert create.call_count == 2


def test_naming_a_contact_rewrites_and_reaches_the_prompt(ctx):
    c, _, _, a = ctx
    with patch.object(nw.client.messages, "create", return_value=_reply(GOOD)) as create:
        c.post(f"/applications/{a.id}/networking")
        r = c.post(f"/applications/{a.id}/networking", json={"contact_name": "Sam Lee", "contact_role": "Recruiter"})
        assert r.json()["cached"] is False and create.call_count == 2
        assert "Sam Lee" in create.call_args.kwargs["messages"][0]["content"]


def test_needs_a_resume_and_hides_other_users_applications(ctx):
    c, user, db, a = ctx
    other = models.User(email=f"o-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="")
    db.add(other); db.commit(); db.refresh(other)
    app.dependency_overrides[get_current_user] = lambda: other
    assert c.post(f"/applications/{a.id}/networking").status_code == 404
    mine = models.Application(user_id=other.id, job_id=a.job_id)
    db.add(mine); db.commit(); db.refresh(mine)
    assert c.post(f"/applications/{mine.id}/networking").status_code == 400


def test_failure_is_refunded_and_nothing_saved(ctx):
    from app.services import usage
    c, user, db, a = ctx
    before = usage.get_usage(db, user.id, "networking")
    with patch.object(nw.client.messages, "create", return_value=_reply("sorry")):
        r = c.post(f"/applications/{a.id}/networking")
    assert r.status_code == 502 and "wasn't counted" in r.json()["detail"]
    db.expire_all()
    assert usage.get_usage(db, user.id, "networking") == before
    assert not db.get(models.Application, a.id).networking_data
