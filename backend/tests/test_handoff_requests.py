"""Tests for the handoff-to-a-human endpoints (GET .../handoff-contacts,
POST .../handoff) -- had no test coverage at all before this, despite
predating this session. Added now because flash mentoring (#54) makes
this a more central, demo-facing flow: "Browse mentors" on the
frontend is a pure presentation layer over these exact two endpoints,
so their correctness now matters more than it used to.

notifier.send_email is mocked throughout -- these tests are about
access control and data correctness, not actually sending email.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models

client = TestClient(app)

_user_counter = [0]
_job_counter = [0]


def _make_user(db):
    _user_counter[0] += 1
    user = models.User(email=f"handoffuser{_user_counter[0]}@x.com", hashed_password="x", full_name="Test User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db):
    _job_counter[0] += 1  # reuse counter for a simple unique join_code too
    org = models.Organization(name="Acme Health", join_code=f"HANDOFF{_job_counter[0]}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


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


def _make_contact(db, org_id, is_mentor=False, mentor_bio=""):
    contact = models.OrgHumanContact(
        organization_id=org_id, name="Pat Contact", email="pat@acme.com",
        description="Office tours", is_mentor=is_mentor, mentor_bio=mentor_bio,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


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


def test_handoff_contacts_includes_mentors_with_bio(db):
    user = _make_user(db)
    org = _make_org(db)
    app_row = _make_application(db, user.id, org.id)
    _make_contact(db, org.id, is_mentor=True, mentor_bio="10 years in ICU nursing")
    _make_contact(db, org.id, is_mentor=False)  # general contact, not a mentor

    _login_as(user)
    resp = client.get(f"/applications/{app_row.id}/handoff-contacts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    mentor_entry = next(c for c in body if c["is_mentor"])
    assert mentor_entry["mentor_bio"] == "10 years in ICU nursing"


def test_handoff_contacts_empty_for_non_org_application(db):
    user = _make_user(db)
    job = _make_job(db)
    app_row = models.Application(user_id=user.id, job_id=job.id, organization_id=None)
    db.add(app_row)
    db.commit()
    db.refresh(app_row)

    _login_as(user)
    resp = client.get(f"/applications/{app_row.id}/handoff-contacts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_handoff_contacts_404_for_someone_elses_application(db):
    owner = _make_user(db)
    outsider = _make_user(db)
    org = _make_org(db)
    app_row = _make_application(db, owner.id, org.id)

    _login_as(outsider)
    resp = client.get(f"/applications/{app_row.id}/handoff-contacts")
    assert resp.status_code == 404


def test_request_handoff_to_a_mentor_succeeds(db):
    user = _make_user(db)
    org = _make_org(db)
    app_row = _make_application(db, user.id, org.id)
    mentor_contact = _make_contact(db, org.id, is_mentor=True, mentor_bio="Career coaching")

    _login_as(user)
    with patch("app.routers.job_buddy.notifier.send_email") as mock_send:
        resp = client.post(
            f"/applications/{app_row.id}/handoff",
            json={"contact_id": mentor_contact.id, "note": "Would love to chat about my career goals."},
        )
    assert resp.status_code == 200
    mock_send.assert_called_once()
    sent_to = mock_send.call_args.args[0]
    assert sent_to == mentor_contact.email

    handoff = db.query(models.HandoffRequest).filter_by(application_id=app_row.id).first()
    assert handoff is not None
    assert handoff.contact_id == mentor_contact.id
    assert handoff.note == "Would love to chat about my career goals."


def test_request_handoff_only_sends_the_employees_own_note_not_chat_history(db):
    """A structural check on the privacy claim in the endpoint's own
    docstring -- the notification email body should contain exactly
    the note text and nothing else that looks like chat content."""
    user = _make_user(db)
    org = _make_org(db)
    app_row = _make_application(db, user.id, org.id)
    contact = _make_contact(db, org.id, is_mentor=True)

    db.add(models.JobBuddyMessage(application_id=app_row.id, user_id=user.id, role="user", content="secret chat content, should never leak"))
    db.commit()

    _login_as(user)
    with patch("app.routers.job_buddy.notifier.send_email") as mock_send:
        client.post(
            f"/applications/{app_row.id}/handoff",
            json={"contact_id": contact.id, "note": "Just my note."},
        )
    email_body = mock_send.call_args.args[2]
    assert "Just my note." in email_body
    assert "secret chat content" not in email_body


def test_request_handoff_404_for_contact_in_different_org(db):
    user = _make_user(db)
    org = _make_org(db)
    other_org = _make_org(db)
    app_row = _make_application(db, user.id, org.id)
    contact_in_other_org = _make_contact(db, other_org.id, is_mentor=True)

    _login_as(user)
    resp = client.post(
        f"/applications/{app_row.id}/handoff",
        json={"contact_id": contact_in_other_org.id, "note": "Hello"},
    )
    assert resp.status_code == 404


def test_request_handoff_graceful_502_on_email_failure(db):
    user = _make_user(db)
    org = _make_org(db)
    app_row = _make_application(db, user.id, org.id)
    contact = _make_contact(db, org.id, is_mentor=True)

    _login_as(user)
    with patch("app.routers.job_buddy.notifier.send_email", side_effect=RuntimeError("SMTP down")):
        resp = client.post(
            f"/applications/{app_row.id}/handoff",
            json={"contact_id": contact.id, "note": "Hello"},
        )
    assert resp.status_code == 502
    # No HandoffRequest row should be created if the email never sent --
    # a "sent" record for a request nobody actually received would be
    # misleading.
    assert db.query(models.HandoffRequest).filter_by(application_id=app_row.id).count() == 0
