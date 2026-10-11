"""The 'sound more human' rewrite: wording changes, facts never do."""
import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import cover_letter as cl, resume_customizer as rc, usage

BLOCKS = [
    {"type": "name", "text": "Pat Example"},
    {"type": "contact", "text": "pat@example.com  |  (312) 555-0100  |  Chicago, IL"},
    {"type": "heading", "text": "Professional Summary"},
    {"type": "text", "text": "Results-driven security leader with a proven track record of leveraging NIST and SOC 2 frameworks across 12 business units."},
    {"type": "heading", "text": "Experience"},
    {"type": "entry", "left": "Security Engineer", "right": "2019 – 2024"},
    {"type": "sub", "text": "Acme — Chicago, IL"},
    {"type": "bullet", "text": "Spearheaded remediation that cut audit findings 40% using AWS tooling."},
    {"type": "skills", "label": "Tools", "text": "AWS, Splunk, NIST"},
]
JOB = {"title": "Lead", "company": "Beta", "description": "NIST SOC 2 audit"}


def _reply(items, note="Plainer words."):
    c = MagicMock()
    c.messages.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({"note": note, "items": items}))])
    return c


GOOD = [
    {"i": 3, "text": "I lead security programs built on NIST and SOC 2, most recently across 12 business units."},
    {"i": 7, "text": "Cut audit findings 40% by fixing the root causes with AWS tooling."},
]


def test_good_rewrite_changes_only_the_wording(monkeypatch):
    monkeypatch.setattr(rc, "client", _reply(GOOD))
    out, note = rc.humanize_blocks(BLOCKS, JOB)
    assert out[3]["text"].startswith("I lead") and out[7]["text"].startswith("Cut audit")
    for i in (0, 1, 2, 4, 5, 6, 8):
        assert out[i] == BLOCKS[i]            # name, contact, headings, role, dates, skills untouched
    assert note


@pytest.mark.parametrize("bad", [
    [{"i": 3, "text": "Security leader across 12 business units using NIST and SOC 2."}, {"i": 7, "text": "Cut audit findings 60% using AWS tooling."}],   # number changed
    [{"i": 3, "text": "Security leader across 12 business units using NIST and SOC 2."}, {"i": 7, "text": "Cut audit findings 40% by fixing root causes."}],  # AWS dropped
    [{"i": 3, "text": "Hi."}, {"i": 7, "text": "Cut audit findings 40% using AWS tooling."}],                                                              # far too short
    [{"i": 3, "text": "I lead security programs built on NIST and SOC 2 across 12 business units."}],                                                      # a line missing
])
def test_unsafe_rewrites_are_refused(monkeypatch, bad):
    monkeypatch.setattr(rc, "client", _reply(bad))
    with pytest.raises(ValueError):
        rc.humanize_blocks(BLOCKS, JOB)


LETTER = ("Dear Hiring Team,\n\nI am writing to express my interest in the Lead role. I cut audit findings 40% across 12 business units "
          "using NIST and AWS tooling at Acme.\n\nI would bring the same discipline to your team and I am excited to contribute.\n\n"
          "Sincerely,\nPat Example")


def _text_client(text):
    c = MagicMock()
    c.messages.create.return_value = MagicMock(content=[MagicMock(text=text)])
    return c


def test_letter_rewrite_keeps_greeting_signoff_and_facts(monkeypatch):
    body = ("At Acme I cut audit findings 40% across 12 business units, using NIST and AWS tooling.\n\n"
            "I'd bring the same steady discipline to your team, and I'd be glad to talk it through.")
    monkeypatch.setattr(rc, "client", _text_client(body))
    out, _ = cl.humanize(LETTER, {"title": "Lead", "company": "Beta"})
    assert out.startswith("Dear Hiring Team,") and out.endswith("Sincerely,\nPat Example")
    assert "At Acme I cut audit findings 40%" in out and "writing to express" not in out


def test_letter_rewrite_that_changes_a_number_is_refused(monkeypatch):
    monkeypatch.setattr(rc, "client", _text_client("At Acme I cut audit findings 60% across 12 business units, using NIST and AWS tooling.\n\nSame discipline here."))
    with pytest.raises(ValueError):
        cl.humanize(LETTER, {"title": "Lead", "company": "Beta"})


@pytest.fixture()
def setup():
    db = SessionLocal()
    user = models.User(email=f"hm-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="r")
    db.add(user); db.commit(); db.refresh(user)
    job = models.Job(source="greenhouse", external_id=uuid.uuid4().hex, company="Beta", title="Lead",
                     description="NIST SOC 2 audit", url="https://x.example/3")
    db.add(job); db.commit()
    a = models.Application(user_id=user.id, job_id=job.id, status="pending_approval", tailored_resume_path="B.docx",
                           tailored_resume_data=rc.build_docx_from_blocks(BLOCKS), cover_letter=LETTER)
    db.add(a); db.commit(); db.refresh(a)
    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, a, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_resume_endpoint_proposes_without_saving_and_meters(setup, monkeypatch):
    db, user, a, client = setup
    monkeypatch.setattr(rc, "client", _reply(GOOD))
    before = a.tailored_resume_data
    r = client.post(f"/applications/{a.id}/tailored-resume/humanize")
    assert r.status_code == 200, r.text
    assert r.json()["blocks"][3]["text"].startswith("I lead")
    db.expire_all()
    assert db.get(models.Application, a.id).tailored_resume_data == before
    assert usage.get_usage(db, user.id, "tailor_resume") == 1


def test_resume_refusal_is_not_charged(setup, monkeypatch):
    db, user, a, client = setup
    monkeypatch.setattr(rc, "client", _reply([{"i": 3, "text": "x"}]))
    assert client.post(f"/applications/{a.id}/tailored-resume/humanize").status_code == 502
    assert usage.get_usage(db, user.id, "tailor_resume") == 0


def test_letter_endpoint_proposes_without_saving(setup, monkeypatch):
    db, user, a, client = setup
    monkeypatch.setattr(rc, "client", _text_client("At Acme I cut audit findings 40% across 12 business units, using NIST and AWS tooling.\n\nI'd bring the same steady discipline here, and I'd be glad to talk it through."))
    r = client.post(f"/applications/{a.id}/cover-letter/humanize")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(models.Application, a.id).cover_letter == LETTER
    assert usage.get_usage(db, user.id, "interview_prep") == 1
