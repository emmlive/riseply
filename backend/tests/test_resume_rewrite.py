"""Rewrite a saved resume toward a direction: new text only, nothing invented, metered, own resumes only."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import resume_rewrite as rr, usage

SRC = ("Jane Doe\njane@x.com | Chicago, IL\n\nExperience\nSenior Developer, Acme (2018 - 2024)\n"
       "- Built payment APIs handling 40% more volume\n- Led SOX and ITGC reviews for 12 systems\n"
       "- Designed network segmentation with firewall and SIEM tooling\nEducation\nBS Accounting, 2012\n")
GOOD = ("LABEL: Security Architect resume\n---\nJane Doe\njane@x.com | Chicago, IL\n\nSecurity Architect\nExperience\n"
        "Senior Developer, Acme (2018 - 2024)\n- Designed network segmentation with firewall and SIEM tooling\n"
        "- Led SOX and ITGC reviews for 12 systems\n- Built payment APIs handling 40% more volume\nEducation\nBS Accounting, 2012\n")
BAD = GOOD.replace("Security Architect\n", "Security Architect, CISSP, 25 years\n")


def _reply(text):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_parse_and_unsupported():
    assert rr.parse(GOOD)[0] == "Security Architect resume"
    assert rr.parse("no label here") is None
    assert rr.unsupported(SRC, None, GOOD.split("---\n", 1)[1]) == []
    bad = rr.unsupported(SRC, None, BAD.split("---\n", 1)[1])
    assert "CISSP" in bad and "25" in bad   # a new credential and a new number are both caught
    assert rr.unsupported(SRC, [{"skill": "CISSP", "detail": "certified"}], BAD.split("---\n", 1)[1].replace("25 years", "")) == []


def test_rewrite_retries_once_then_refuses_invention():
    with patch.object(rr.client.messages, "create", side_effect=[_reply(BAD), _reply(GOOD)]) as m:
        label, text = rr.rewrite(SRC, "Security Architect", None)
    assert label == "Security Architect resume" and "CISSP" not in text
    assert "CISSP" in m.call_args_list[1].args[0] if m.call_args_list[1].args else "CISSP" in m.call_args_list[1].kwargs["messages"][0]["content"]
    with patch.object(rr.client.messages, "create", return_value=_reply(BAD)):
        with pytest.raises(ValueError):
            rr.rewrite(SRC, "Security Architect", None)


@pytest.fixture()
def setup():
    db = SessionLocal()
    u = models.User(email=f"rw-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text=SRC)
    db.add(u); db.commit(); db.refresh(u)
    r = models.Resume(user_id=u.id, label="Main", resume_text=SRC, is_default=True)
    db.add(r); db.commit(); db.refresh(r)
    app.dependency_overrides[get_current_user] = lambda: u
    yield db, u, r, TestClient(app)
    app.dependency_overrides.clear(); db.close()


def test_endpoint_returns_a_draft_and_saves_nothing(setup):
    db, u, r, client = setup
    with patch.object(rr.client.messages, "create", return_value=_reply(GOOD)):
        res = client.post("/resumes/rewrite", json={"focus": "Security Architect; not a developer"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["label"] == "Security Architect resume" and body["base_label"] == "Main" and "Security Architect" in body["resume_text"]
    assert db.query(models.Resume).filter_by(user_id=u.id).count() == 1
    assert usage.get_usage(db, u.id, "resume_rewrite") == 1


def test_refused_rewrite_refunds_and_others_resumes_are_not_found(setup):
    db, u, r, client = setup
    with patch.object(rr.client.messages, "create", return_value=_reply(BAD)):
        res = client.post("/resumes/rewrite", json={"focus": "Security Architect"})
    assert res.status_code == 502 and "unchanged" in res.json()["detail"]
    assert usage.get_usage(db, u.id, "resume_rewrite") == 0
    assert client.post("/resumes/rewrite", json={"focus": "Security Architect", "resume_id": 99999999}).status_code == 404
    assert client.post("/resumes/rewrite", json={"focus": "short"}).status_code == 422


def test_resume_list_loads_even_with_null_columns(setup):
    """Older rows can have NULL label/file_name; the list must still load."""
    db, u, r, client = setup
    old = models.Resume(user_id=u.id, label=None, resume_text="Old resume text", is_default=None, file_name=None)
    db.add(old); db.commit()
    res = client.get("/resumes")
    assert res.status_code == 200, res.text
    row = next(x for x in res.json() if x["id"] == old.id)
    assert row["label"] == "" and row["file_name"] == "" and row["is_default"] is False
