import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.config import settings
from app.database import SessionLocal, get_db
from app.main import app
from app.security import get_current_user
from app.services import autopilot, resume_customizer

NOW = datetime(2026, 11, 12, 20, 0)
GOOD_URL = "https://boards.greenhouse.io/acme/jobs/1"


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(settings, "auto_submit_enabled", True)
    s = SessionLocal()
    s.query(models.User).update({models.User.autopilot_enabled: False})  # other tests' people must not take part
    s.commit()
    yield s
    s.close()
    app.dependency_overrides.clear()


def _resume():
    return resume_customizer.build_docx_from_blocks([
        {"type": "name", "text": "Em O"}, {"type": "contact", "text": "e@example.com | 240-555-0100 | Chicago, IL"},
        {"type": "heading", "text": "Experience"}, {"type": "entry", "left": "Auditor, Acme", "right": "2019 - Present"},
    ])


def _user(db, **kw):
    base = dict(email=f"ap-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", full_name="Em O",
                resume_text="r", phone="2405550100", location="Chicago", autopilot_enabled=True,
                autopilot_consent_at=NOW - timedelta(days=1), autopilot_min_score=85, autopilot_daily_cap=5)
    base.update(kw)
    u = models.User(**base)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _match(db, user, score=90, url=GOOD_URL, company="Acme", resume=True, **kw):
    j = models.Job(source="t", external_id=uuid.uuid4().hex, company=company, title="Security Analyst", location="Remote", url=url)
    db.add(j); db.commit()
    a = models.Application(user_id=user.id, job_id=j.id, match_score=score, status="pending_approval",
                           tailored_resume_data=_resume() if resume else None, **kw)
    db.add(a); db.commit(); db.refresh(a)
    return a


def _ok(*a, **k):
    return {"status": "submitted", "detail": "ok"}


def _run(db, runner=_ok, now=NOW):
    with patch("app.services.autopilot.notifier.send_email") as mail:
        out = autopilot.run(db, now, runner=runner)
    return out, mail


def test_applies_to_a_strong_supported_match_records_it_and_emails_the_person(db):
    u = _user(db)
    a = _match(db, u)
    out, mail = _run(db)
    db.refresh(a)
    assert out["applied"] == 1 and a.status == "submitted" and a.auto_applied_at == NOW and a.notes == "Applied by Autopilot."
    assert mail.call_args.args[0] == u.email and "applied for you" in mail.call_args.args[1] and mail.call_args.kwargs["kind"] == "autopilot"


@pytest.mark.parametrize("why,build", [
    ("below the person's score", lambda db, u: _match(db, u, score=80)),
    ("linkedin", lambda db, u: _match(db, u, url="https://www.linkedin.com/jobs/view/1")),
    ("unsupported site", lambda db, u: _match(db, u, url="https://example.com/jobs/1")),
    ("no tailored resume", lambda db, u: _match(db, u, resume=False)),
])
def test_it_leaves_these_for_the_person(db, why, build):
    u = _user(db)
    a = build(db, u)
    out, mail = _run(db, runner=lambda *x, **k: pytest.fail("must not try"))
    db.refresh(a)
    assert a.status == "pending_approval" and a.autopilot_tried_at is None and out["applied"] == 0 and not mail.called


def test_off_without_consent_or_the_switch(db, monkeypatch):
    a = _match(db, _user(db, autopilot_consent_at=None))
    assert _run(db, runner=lambda *x, **k: pytest.fail("no consent"))[0]["applied"] == 0
    b = _match(db, _user(db, autopilot_enabled=False))
    assert _run(db, runner=lambda *x, **k: pytest.fail("off"))[0]["applied"] == 0
    monkeypatch.setattr(settings, "auto_submit_enabled", False)
    _match(db, _user(db))
    assert _run(db, runner=lambda *x, **k: pytest.fail("kill switch"))[0]["stopped"] == "disabled"
    db.refresh(a); db.refresh(b)
    assert a.status == b.status == "pending_approval"


def test_floor_beats_a_lower_chosen_score(db):
    u = _user(db, autopilot_min_score=60)
    a = _match(db, u, score=70)
    assert _run(db, runner=lambda *x, **k: pytest.fail("below the 75 floor"))[0]["applied"] == 0
    db.refresh(a)
    assert a.status == "pending_approval"


def test_daily_cap_and_best_matches_go_first(db):
    u = _user(db, autopilot_daily_cap=2)
    low, mid, top = _match(db, u, 86, company="A"), _match(db, u, 90, company="B"), _match(db, u, 97, company="C")
    out, _ = _run(db)
    for x in (low, mid, top):
        db.refresh(x)
    assert out["applied"] == 2 and top.status == mid.status == "submitted" and low.status == "pending_approval"
    out2, _ = _run(db, now=NOW + timedelta(hours=1))
    assert out2["applied"] == 0, "cap is per rolling day"
    out3, _ = _run(db, now=NOW + timedelta(hours=25))
    db.refresh(low)
    assert out3["applied"] == 1 and low.status == "submitted"


def test_a_form_that_needs_a_person_goes_back_with_a_reason_and_is_not_retried(db):
    u = _user(db)
    a = _match(db, u)
    calls = []

    def needs_you(*x, **k):
        calls.append(1)
        return {"status": "needs_manual_review", "detail": "Needs your answer to: Are you legally authorized to work here?."}
    out, mail = _run(db, runner=needs_you)
    db.refresh(a)
    assert out["handed_back"] == 1 and a.status == "pending_approval" and a.autopilot_tried_at == NOW
    assert "legally authorized" in a.notes and "ready for you to review" in a.notes and not mail.called
    _run(db, runner=needs_you, now=NOW + timedelta(hours=1))
    assert len(calls) == 1, "each application is tried once"


def test_a_crash_never_stops_the_run_or_marks_it_applied(db):
    u = _user(db)
    a, b = _match(db, u, 95, company="A"), _match(db, u, 90, company="B")
    seq = iter([RuntimeError("boom"), {"status": "submitted", "detail": "ok"}])

    def flaky(*x, **k):
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v
    out, _ = _run(db, runner=flaky)
    db.refresh(a); db.refresh(b)
    assert a.status == "pending_approval" and "boom" in a.notes and b.status == "submitted" and out["applied"] == 1


def test_no_second_application_to_the_same_company_soon(db):
    u = _user(db)
    first = _match(db, u, 95, company="Acme")
    second = _match(db, u, 92, company="acme")
    out, _ = _run(db)
    db.refresh(first); db.refresh(second)
    assert out["applied"] == 1 and first.status == "submitted" and second.status == "pending_approval"


def test_browser_that_will_not_start_stops_the_whole_run(db):
    u = _user(db)
    a, b = _match(db, u, 95, company="A"), _match(db, u, 90, company="B")
    calls = []

    def down(*x, **k):
        calls.append(1)
        return {"status": "failed", "detail": "Couldn't start the browser: no chromium"}
    out, _ = _run(db, runner=down)
    assert out["stopped"] == "browser_unavailable" and len(calls) == 1


def test_a_resume_with_no_readable_contact_details_is_not_sent(db):
    u = _user(db)
    a = _match(db, u)
    a.tailored_resume_data = resume_customizer.build_docx_from_blocks([{"type": "name", "text": "Em O"}, {"type": "heading", "text": "Experience"}])
    db.commit()
    assert _run(db, runner=lambda *x, **k: pytest.fail("no contact details"))[0]["applied"] == 0


# ---- settings and the trigger ----

def _client(db, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_turning_autopilot_on_needs_a_resume_contact_details_and_confirmation(db):
    c = _client(db, _user(db, autopilot_enabled=False, autopilot_consent_at=None, resume_text=""))
    assert c.patch("/me", json={"autopilot_enabled": True, "autopilot_consent": True}).status_code == 400
    u = _user(db, autopilot_enabled=False, autopilot_consent_at=None, phone="")
    c = _client(db, u)
    assert "phone" in c.patch("/me", json={"autopilot_enabled": True, "autopilot_consent": True}).json()["detail"]
    u.phone = "2405550100"; u.location = "Chicago"; db.commit()
    r = c.patch("/me", json={"autopilot_enabled": True})
    assert r.status_code == 400 and "Confirm" in r.json()["detail"]
    ok = c.patch("/me", json={"autopilot_enabled": True, "autopilot_consent": True, "phone": "2405550100", "location": "Chicago",
                              "autopilot_min_score": 90, "autopilot_daily_cap": 3})
    assert ok.status_code == 200 and ok.json()["autopilot_enabled"] and ok.json()["autopilot_min_score"] == 90
    db.refresh(u)
    assert u.autopilot_consent_at is not None
    assert c.patch("/me", json={"autopilot_min_score": 60}).status_code == 422
    assert c.patch("/me", json={"autopilot_daily_cap": 50}).status_code == 422
    assert c.patch("/me", json={"autopilot_enabled": False}).json()["autopilot_enabled"] is False


def test_hourly_trigger_needs_the_secret_and_only_starts_when_switched_on(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    c = TestClient(app)
    assert c.post("/internal/run-autopilot").status_code == 401
    with patch("app.services.autopilot.run_background") as bg:
        r = c.post("/internal/run-autopilot", headers={"X-Cron-Secret": "s3cret"})
        assert r.status_code == 202 and r.json() == {"started": True} and bg.called
        monkeypatch.setattr(settings, "auto_submit_enabled", False)
        bg.reset_mock()
        r = c.post("/internal/run-autopilot", headers={"X-Cron-Secret": "s3cret"})
        assert r.json()["started"] is False and not bg.called


def test_apply_queue_lists_open_strong_matches_best_first_with_autopilot_notes(db):
    u = _user(db, autopilot_enabled=False)
    best = _match(db, u, 95, url="https://jobs.lever.co/x/1")
    mid = _match(db, u, 72, url="https://example.com/job", resume=False)
    handed = _match(db, u, 80, notes="Autopilot didn't send this one: Needs your answer to: Visa. It is ready for you to review.")
    _match(db, u, 50)                                            # too weak to queue
    done = _match(db, u, 99); done.status = "submitted"; done.submitted_at = NOW; done.auto_applied_at = NOW
    closed = _match(db, u, 98)
    db.get(models.Job, closed.job_id).is_active = False
    db.commit()
    with patch("app.routers.pipeline.datetime") as dt:
        dt.utcnow.return_value = NOW + timedelta(days=1)
        r = _client(db, u).get("/applications/apply-queue")
    body = r.json()
    assert [x["id"] for x in body["items"]] == [best.id, handed.id, mid.id]
    assert body["items"][0]["autopilot_ok"] is True and body["items"][2]["autopilot_ok"] is False and body["items"][2]["has_resume"] is False
    assert "Needs your answer" in body["items"][1]["note"]
    assert body["applied_this_week"] == 1 and body["autopilot_applied_this_week"] == 1
