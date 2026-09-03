"""Tests for pulse check-ins -- PulseCheckIn, the employee-facing
pending-checkin/respond endpoints, the admin-facing aggregate summary
(with its minimum-respondent anonymity threshold), and the recurring
creation cron.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import pulse_checkins

client = TestClient(app)

_user_counter = [0]
_org_counter = [0]
_job_counter = [0]


def _make_user(db):
    _user_counter[0] += 1
    user = models.User(email=f"pulseuser{_user_counter[0]}@x.com", hashed_password="x", full_name=f"User {_user_counter[0]}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db):
    _org_counter[0] += 1
    org = models.Organization(name="Pulse Health", join_code=f"PULSEORG{_org_counter[0]}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_member(db, org_id, user_id, role="admin"):
    member = models.OrganizationMember(organization_id=org_id, user_id=user_id, role=role)
    db.add(member)
    db.commit()
    return member


def _make_job(db):
    import uuid
    job = models.Job(source="test", external_id=uuid.uuid4().hex, company="Acme", title="Nurse", location="Remote")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _make_application(db, user_id, org_id=None, is_archived=False):
    job = _make_job(db)
    app_row = models.Application(user_id=user_id, job_id=job.id, organization_id=org_id, is_archived=is_archived)
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return app_row


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _login_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _make_org_with_admin_and_employee(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id)
    return admin, org, employee, employee_app


# --- employee-facing ---

def test_no_pending_checkin_returns_null(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(employee)
    resp = client.get(f"/applications/{employee_app.id}/pulse-checkins/pending")
    assert resp.status_code == 200
    assert resp.json() is None


def test_pending_checkin_returned_when_one_exists(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    db.add(models.PulseCheckIn(application_id=employee_app.id))
    db.commit()

    _login_as(employee)
    resp = client.get(f"/applications/{employee_app.id}/pulse-checkins/pending")
    assert resp.status_code == 200
    assert resp.json() is not None


def test_answered_checkin_not_returned_as_pending(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    db.add(models.PulseCheckIn(application_id=employee_app.id, responded_at=datetime.utcnow(), sentiment="great"))
    db.commit()

    _login_as(employee)
    resp = client.get(f"/applications/{employee_app.id}/pulse-checkins/pending")
    assert resp.json() is None


def test_employee_can_respond(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    checkin = models.PulseCheckIn(application_id=employee_app.id)
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    _login_as(employee)
    resp = client.post(
        f"/applications/{employee_app.id}/pulse-checkins/{checkin.id}/respond",
        json={"sentiment": "okay", "comment": "Things are fine, a bit slow to get set up."},
    )
    assert resp.status_code == 200

    db.refresh(checkin)
    assert checkin.sentiment == "okay"
    assert checkin.comment == "Things are fine, a bit slow to get set up."
    assert checkin.responded_at is not None


def test_cannot_respond_to_already_answered_checkin(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    checkin = models.PulseCheckIn(application_id=employee_app.id, responded_at=datetime.utcnow(), sentiment="great")
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/pulse-checkins/{checkin.id}/respond", json={"sentiment": "okay"})
    assert resp.status_code == 400


def test_respond_rejects_invalid_sentiment(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    checkin = models.PulseCheckIn(application_id=employee_app.id)
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/pulse-checkins/{checkin.id}/respond", json={"sentiment": "amazing"})
    assert resp.status_code == 422


def test_cannot_respond_to_someone_elses_checkin(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    outsider = _make_user(db)
    outsider_app = _make_application(db, outsider.id)
    checkin = models.PulseCheckIn(application_id=employee_app.id)
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    _login_as(outsider)
    resp = client.post(f"/applications/{outsider_app.id}/pulse-checkins/{checkin.id}/respond", json={"sentiment": "great"})
    assert resp.status_code == 404


# --- admin summary ---

def test_summary_hidden_below_min_respondents(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    db.add(models.PulseCheckIn(application_id=employee_app.id, responded_at=datetime.utcnow(), sentiment="great"))
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/pulse-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_responded"] == 1
    assert body["great_pct"] is None  # below MIN_PULSE_RESPONDENTS


def test_summary_shown_once_enough_respondents(db):
    from app.routers.org_buddy import MIN_PULSE_RESPONDENTS

    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    for _ in range(MIN_PULSE_RESPONDENTS):
        emp = _make_user(db)
        emp_app = _make_application(db, emp.id, org.id)
        db.add(models.PulseCheckIn(application_id=emp_app.id, responded_at=datetime.utcnow(), sentiment="great"))
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/pulse-summary")
    body = resp.json()
    assert body["great_pct"] == 100.0


def test_summary_response_rate_reflects_unanswered_checkins(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    db.add(models.PulseCheckIn(application_id=employee_app.id, responded_at=datetime.utcnow(), sentiment="great"))
    db.add(models.PulseCheckIn(application_id=employee_app.id))  # sent, not yet answered
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/pulse-summary")
    body = resp.json()
    assert body["total_sent"] == 2
    assert body["total_responded"] == 1
    assert body["response_rate_pct"] == 50.0


def test_summary_requires_admin(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(employee)
    resp = client.get(f"/orgs/{org.id}/pulse-summary")
    assert resp.status_code == 403


def test_summary_never_includes_comment_text(db):
    """A blunt but important check -- the private comment text must
    never appear anywhere in the admin summary response."""
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    secret_text = "MySpecificPrivateGrievanceAboutMyManager"
    db.add(models.PulseCheckIn(application_id=employee_app.id, responded_at=datetime.utcnow(), sentiment="struggling", comment=secret_text))
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/pulse-summary")
    assert secret_text not in resp.text


# --- creation cron ---

def test_cron_creates_checkin_for_employee_with_none_yet(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    with patch("app.services.notifier.send_email"):
        result = pulse_checkins.run_pulse_checkin_creation(db)

    assert result["pulse_checkins_created"] >= 1
    checkin = db.query(models.PulseCheckIn).filter_by(application_id=employee_app.id).first()
    assert checkin is not None


def test_cron_does_not_duplicate_a_recent_checkin(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    db.add(models.PulseCheckIn(application_id=employee_app.id, sent_at=datetime.utcnow() - timedelta(days=5)))
    db.commit()

    with patch("app.services.notifier.send_email"):
        pulse_checkins.run_pulse_checkin_creation(db)

    count = db.query(models.PulseCheckIn).filter_by(application_id=employee_app.id).count()
    assert count == 1  # the recent one, not a duplicate


def test_cron_creates_new_checkin_once_interval_has_passed(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    db.add(models.PulseCheckIn(application_id=employee_app.id, sent_at=datetime.utcnow() - timedelta(days=45)))
    db.commit()

    with patch("app.services.notifier.send_email"):
        pulse_checkins.run_pulse_checkin_creation(db)

    count = db.query(models.PulseCheckIn).filter_by(application_id=employee_app.id).count()
    assert count == 2  # the old one plus a fresh one


def test_cron_skips_archived_applications(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db)
    archived_app = _make_application(db, employee.id, org.id, is_archived=True)

    with patch("app.services.notifier.send_email"):
        pulse_checkins.run_pulse_checkin_creation(db)

    count = db.query(models.PulseCheckIn).filter_by(application_id=archived_app.id).count()
    assert count == 0
