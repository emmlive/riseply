"""Tests for mentor meeting scheduling (POST/GET .../schedule,
DELETE .../mentor-meeting-schedules/{id}) -- Week 2 of the October
demo calendar-sync feature (#52).

calendar_oauth's actual Graph API calls (create_event, cancel_event,
get_valid_access_token's refresh path) are mocked throughout; these
tests are about the scheduling logic -- which candidate's calendar
connection gets used, graceful degradation when neither party is
connected or a Graph call fails, access control, and cancellation --
not about Microsoft's API itself.
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import calendar_oauth, calendar_encryption

client = TestClient(app)

_user_counter = [0]
_job_counter = [0]


def _make_user(db, email=None):
    _user_counter[0] += 1
    email = email or f"schuser{_user_counter[0]}@x.com"
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


_org_counter = [0]


def _make_org(db, name):
    # join_code decoupled from `name` entirely -- an earlier version of
    # this file used name[:5], and every org name here shared "Sched"
    # as its first 5 characters (SchedA, SchedB, ...), so they all
    # produced the identical join_code and collided on Organization's
    # unique constraint. A counter has no such risk regardless of what
    # names get chosen later.
    _org_counter[0] += 1
    org = models.Organization(name=name, join_code=f"SCHED{_org_counter[0]}")
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


def _make_application(db, user_id, org_id):
    job = _make_job(db)
    app_row = models.Application(user_id=user_id, job_id=job.id, organization_id=org_id)
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return app_row


def _make_mentor_contact(db, org_id, name="Mentor One"):
    contact = models.OrgHumanContact(
        organization_id=org_id, name=name, email=f"{name.replace(' ', '').lower()}@acme.com",
        is_mentor=True, mentor_bio="Experienced",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def _make_connection(db, user_id):
    conn = models.CalendarConnection(
        user_id=user_id, provider="microsoft",
        access_token=calendar_encryption.encrypt_token("valid-token"),
        refresh_token=calendar_encryption.encrypt_token("valid-refresh"),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(conn)
    db.commit()
    return conn


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


def _make_pairing(db, org_name):
    admin = _make_user(db)
    org = _make_org(db, org_name)
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db)
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return admin, org, employee, contact, assignment


def test_schedule_without_any_calendar_connection(db):
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedA")
    _login_as(employee)

    future = datetime.utcnow() + timedelta(days=2)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule",
        json={"scheduled_at": future.isoformat(), "duration_minutes": 30},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["calendar_event_created"] is False
    assert body["cancelled_at"] is None


def test_schedule_uses_schedulers_own_connection(db, monkeypatch):
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedB")
    _make_connection(db, employee.id)
    _login_as(employee)

    created_with = {}

    def fake_create_event(access_token, subject, start, duration_minutes, attendee_emails):
        created_with["attendees"] = attendee_emails
        return "event-abc-123"

    monkeypatch.setattr(calendar_oauth, "create_event", fake_create_event)

    future = datetime.utcnow() + timedelta(days=2)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule",
        json={"scheduled_at": future.isoformat(), "duration_minutes": 45},
    )
    assert resp.status_code == 200
    assert resp.json()["calendar_event_created"] is True
    # The mentor's email should be invited, the employee's own email
    # (the token owner) should NOT be duplicated into the attendee list.
    assert contact.email in created_with["attendees"]
    assert employee.email not in created_with["attendees"]


def test_schedule_falls_back_to_other_partys_connection(db, monkeypatch):
    """Scheduler (employee) has no connection, but a User account
    matching the mentor's contact email does -- the event should still
    get created, on the mentor's calendar."""
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedC")
    mentor_user = _make_user(db, email=contact.email)  # mentor has their own Riseply login
    _make_connection(db, mentor_user.id)
    _login_as(employee)

    monkeypatch.setattr(calendar_oauth, "create_event", lambda access_token, **kw: "event-xyz")

    future = datetime.utcnow() + timedelta(days=2)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule",
        json={"scheduled_at": future.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["calendar_event_created"] is True


def test_schedule_degrades_gracefully_on_graph_api_failure(db, monkeypatch):
    """A calendar failure shouldn't fail the whole request -- the
    meeting still gets scheduled, just without an invite."""
    from fastapi import HTTPException
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedD")
    _make_connection(db, employee.id)
    _login_as(employee)

    def boom(access_token, **kw):
        raise HTTPException(status_code=502, detail="Graph API is down")

    monkeypatch.setattr(calendar_oauth, "create_event", boom)

    future = datetime.utcnow() + timedelta(days=2)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule",
        json={"scheduled_at": future.isoformat()},
    )
    assert resp.status_code == 200  # NOT a 502 -- degrades gracefully
    assert resp.json()["calendar_event_created"] is False


def test_schedule_requires_pairing_access(db):
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedE")
    outsider = _make_user(db)
    _login_as(outsider)

    future = datetime.utcnow() + timedelta(days=2)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule",
        json={"scheduled_at": future.isoformat()},
    )
    assert resp.status_code == 403


def test_list_scheduled_meetings_excludes_cancelled(db):
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedF")
    _login_as(employee)

    future1 = (datetime.utcnow() + timedelta(days=1)).isoformat()
    future2 = (datetime.utcnow() + timedelta(days=3)).isoformat()
    r1 = client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule", json={"scheduled_at": future1})
    client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule", json={"scheduled_at": future2})

    client.delete(f"/orgs/{org.id}/mentor-meeting-schedules/{r1.json()['id']}")

    resp = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1  # the cancelled one is excluded


def test_cancel_attempts_calendar_event_cancellation(db, monkeypatch):
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedG")
    _make_connection(db, employee.id)
    _login_as(employee)

    monkeypatch.setattr(calendar_oauth, "create_event", lambda access_token, **kw: "event-to-cancel")
    future = (datetime.utcnow() + timedelta(days=2)).isoformat()
    created = client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/schedule", json={"scheduled_at": future})
    schedule_id = created.json()["id"]

    cancel_calls = []
    monkeypatch.setattr(calendar_oauth, "cancel_event", lambda token, event_id: cancel_calls.append(event_id))

    resp = client.delete(f"/orgs/{org.id}/mentor-meeting-schedules/{schedule_id}")
    assert resp.status_code == 200
    assert cancel_calls == ["event-to-cancel"]


def test_cancel_404_for_unknown_schedule(db):
    admin, org, employee, contact, assignment = _make_pairing(db, "SchedH")
    _login_as(employee)

    resp = client.delete(f"/orgs/{org.id}/mentor-meeting-schedules/999999")
    assert resp.status_code == 404
