"""Marking an application as interviewing prepares the person in the background:
prep brief (metered, refunded on failure) and a next-steps email."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import interview_auto, usage


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"ia-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="SOC analyst")
    db.add(user); db.commit(); db.refresh(user)
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title="Security Analyst", company="Acme", description="d")
    db.add(job); db.commit(); db.refresh(job)
    a = models.Application(user_id=user.id, job_id=job.id, status="interviewing")
    db.add(a); db.commit(); db.refresh(a)
    yield db, user, a
    db.close()


def test_writes_prep_counts_it_and_emails_the_next_steps(ctx):
    db, user, a = ctx
    before = usage.get_usage(db, user.id, "interview_prep")
    with patch.object(interview_auto.interview_prep_service, "generate_prep_brief", return_value="BRIEF") as gen, \
            patch.object(interview_auto.notifier, "send_email") as send:
        interview_auto.prepare(a.id)
    assert gen.call_count == 1
    db.expire_all()
    assert db.query(models.InterviewPrep).filter_by(application_id=a.id).first().brief == "BRIEF"
    assert usage.get_usage(db, user.id, "interview_prep") == before + 1
    subject, body = send.call_args.args[1], send.call_args.args[2]
    assert "Security Analyst @ Acme" in subject and "mock interview" in body and "ready on your Applications page" in body
    assert "type=negotiation" in body


def test_failed_prep_is_refunded_and_the_email_still_goes_out(ctx):
    db, user, a = ctx
    before = usage.get_usage(db, user.id, "interview_prep")
    with patch.object(interview_auto.interview_prep_service, "generate_prep_brief", side_effect=RuntimeError("down")), \
            patch.object(interview_auto.notifier, "send_email") as send:
        interview_auto.prepare(a.id)
    db.expire_all()
    assert usage.get_usage(db, user.id, "interview_prep") == before
    assert not db.query(models.InterviewPrep).filter_by(application_id=a.id).first()
    assert "click Interview prep" in send.call_args.args[2]


def test_existing_prep_is_not_regenerated(ctx):
    db, user, a = ctx
    db.add(models.InterviewPrep(application_id=a.id, user_id=user.id, brief="OLD")); db.commit()
    with patch.object(interview_auto.interview_prep_service, "generate_prep_brief") as gen, \
            patch.object(interview_auto.notifier, "send_email"):
        interview_auto.prepare(a.id)
    assert gen.call_count == 0


def test_respects_notifications_off_and_skips_other_statuses(ctx):
    db, user, a = ctx
    user.notification_preference = "off"; db.commit()
    with patch.object(interview_auto.interview_prep_service, "generate_prep_brief", return_value="B"), \
            patch.object(interview_auto.notifier, "send_email") as send:
        interview_auto.prepare(a.id)
        assert send.call_count == 0
        a.status = "approved"; db.commit()
        user.notification_preference = "every_match"; db.commit()
        interview_auto.prepare(a.id)
        assert send.call_count == 0


def test_marking_interviewing_schedules_it_once(ctx):
    db, user, a = ctx
    a.status = "submitted"; db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        c = TestClient(app)
        with patch.object(interview_auto, "prepare") as prep:
            assert c.post(f"/applications/{a.id}/mark-interviewing").status_code == 200
            assert c.post(f"/applications/{a.id}/mark-interviewing").status_code == 200
        assert prep.call_count == 1
    finally:
        app.dependency_overrides.clear()
