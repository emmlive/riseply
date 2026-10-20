"""Quiet-application nudges: one email per person, once per application, no AI."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from app import models
from app.database import SessionLocal
from app.services import follow_up_nudges as fn


def _user(db, **kw):
    u = models.User(email=f"fn-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", **kw)
    db.add(u); db.commit(); db.refresh(u); return u


def _app(db, user, days, status="submitted", title="Analyst", **kw):
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title=title, company="Acme", description="d")
    db.add(job); db.commit(); db.refresh(job)
    a = models.Application(user_id=user.id, job_id=job.id, status=status,
                           submitted_at=datetime.utcnow() - timedelta(days=days), **kw)
    db.add(a); db.commit(); db.refresh(a); return a


def test_one_email_lists_due_applications_and_marks_them_once():
    db = SessionLocal()
    u = _user(db)
    due1, due2 = _app(db, u, 9, title="SOC Analyst"), _app(db, u, 14, title="IR Lead")
    fresh, old, interviewing = _app(db, u, 3), _app(db, u, 60), _app(db, u, 10, status="interviewing")
    with patch.object(fn.notifier, "send_email") as send:
        out = fn.run_follow_up_nudges(db)
        mine = [c for c in send.call_args_list if c.args[0] == u.email]
        assert len(mine) == 1 and "2 applications waiting" in mine[0].args[1]
        assert "SOC Analyst at Acme" in mine[0].args[2] and "IR Lead at Acme" in mine[0].args[2]
        send.reset_mock()
        fn.run_follow_up_nudges(db)
        assert not [c for c in send.call_args_list if c.args[0] == u.email]  # never twice
    db.expire_all()
    assert db.get(models.Application, due1.id).follow_up_nudged_at and db.get(models.Application, due2.id).follow_up_nudged_at
    for a in (fresh, old, interviewing):
        assert db.get(models.Application, a.id).follow_up_nudged_at is None
    db.close()


def test_caps_the_email_and_carries_the_rest_to_the_next_run():
    db = SessionLocal()
    u = _user(db)
    for i in range(7):
        _app(db, u, 8 + i, title=f"Role {i}")
    with patch.object(fn.notifier, "send_email") as send:
        fn.run_follow_up_nudges(db)
        first = [c for c in send.call_args_list if c.args[0] == u.email]
        assert "5 applications" in first[0].args[1]
        send.reset_mock()
        fn.run_follow_up_nudges(db)
        second = [c for c in send.call_args_list if c.args[0] == u.email]
        assert "2 applications" in second[0].args[1]
    db.close()


def test_respects_notifications_off_and_failed_sends_retry_tomorrow():
    db = SessionLocal()
    off = _user(db, notification_preference="off")
    a_off = _app(db, off, 10)
    flaky = _user(db)
    a_flaky = _app(db, flaky, 10)
    with patch.object(fn.notifier, "send_email", side_effect=RuntimeError("down")) as send:
        fn.run_follow_up_nudges(db)
        assert not [c for c in send.call_args_list if c.args[0] == off.email]
    db.expire_all()
    assert db.get(models.Application, a_off.id).follow_up_nudged_at is not None   # not stored up for later
    assert db.get(models.Application, a_flaky.id).follow_up_nudged_at is None      # will try again
    db.close()
