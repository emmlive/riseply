"""Tests for the manager tier -- GET /orgs/{organization_id}/my-reports.

A genuinely separate, narrower access tier from admin: no
_require_admin/_require_scope_admin call at all, since the query is
self-scoping (can only ever return people whose
Application.manager_email matches the caller's own email). Covers the
basic direct-reports listing, that it's aggregate-only progress data
(checklist %, mentor status, certification counts) reused correctly
from each subsystem's own layering rules, that someone with zero
reports gets an empty list rather than an error, and that a manager
who is NOT an org admin can still see their own reports.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models

client = TestClient(app)

_user_counter = [0]
_org_counter = [0]
_job_counter = [0]


def _make_user(db, email=None):
    _user_counter[0] += 1
    email = email or f"mgruser{_user_counter[0]}@x.com"
    user = models.User(email=email, hashed_password="x", full_name=f"User {_user_counter[0]}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db):
    _org_counter[0] += 1
    org = models.Organization(name="Acme Health", join_code=f"MGRORG{_org_counter[0]}")
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


def _make_application(db, user_id, org_id=None, manager_email="", department_id=None):
    job = _make_job(db)
    app_row = models.Application(
        user_id=user_id, job_id=job.id, organization_id=org_id,
        manager_email=manager_email, department_id=department_id,
    )
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


def test_manager_sees_their_direct_reports(db):
    manager = _make_user(db, "manager1@acme.com")
    org = _make_org(db)
    report_a = _make_user(db)
    report_b = _make_user(db)
    _make_application(db, report_a.id, org.id, manager_email=manager.email)
    _make_application(db, report_b.id, org.id, manager_email=manager.email)

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    emails = {r["user_email"] for r in body}
    assert emails == {report_a.email, report_b.email}


def test_manager_does_not_need_to_be_admin(db):
    """The core point of this being a genuinely separate tier -- no
    OrganizationMember row at all, just an Application listing this
    person as manager_email, and they can still see their reports."""
    manager = _make_user(db, "manager2@acme.com")
    org = _make_org(db)
    report = _make_user(db)
    _make_application(db, report.id, org.id, manager_email=manager.email)

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_someone_with_no_reports_gets_empty_list_not_error(db):
    random_user = _make_user(db, "norep@acme.com")
    org = _make_org(db)

    _login_as(random_user)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    assert resp.status_code == 200
    assert resp.json() == []


def test_manager_only_sees_their_own_reports_not_someone_elses(db):
    manager_a = _make_user(db, "mgra3@acme.com")
    manager_b = _make_user(db, "mgrb3@acme.com")
    org = _make_org(db)
    report_a = _make_user(db)
    report_b = _make_user(db)
    _make_application(db, report_a.id, org.id, manager_email=manager_a.email)
    _make_application(db, report_b.id, org.id, manager_email=manager_b.email)

    _login_as(manager_a)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["user_email"] == report_a.email


def test_checklist_completion_percentage_computed_correctly(db):
    manager = _make_user(db, "manager4@acme.com")
    org = _make_org(db)
    report = _make_user(db)
    report_app = _make_application(db, report.id, org.id, manager_email=manager.email)

    item1 = models.OrgChecklistItem(organization_id=org.id, title="Item 1")
    item2 = models.OrgChecklistItem(organization_id=org.id, title="Item 2")
    db.add_all([item1, item2])
    db.commit()
    db.refresh(item1)
    db.refresh(item2)
    db.add(models.ChecklistCompletion(application_id=report_app.id, checklist_item_id=item1.id))
    db.commit()

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    body = resp.json()
    assert body[0]["checklist_completion_pct"] == 50.0


def test_department_scoped_checklist_item_only_counts_for_that_department(db):
    manager = _make_user(db, "manager5@acme.com")
    org = _make_org(db)
    dept = models.Department(organization_id=org.id, name="ICU", join_code="MGRDEPT5")
    db.add(dept)
    db.commit()
    db.refresh(dept)

    report = _make_user(db)
    report_app = _make_application(db, report.id, org.id, manager_email=manager.email, department_id=None)

    # A department-scoped item shouldn't apply to a company-wide (no
    # department) report at all.
    dept_item = models.OrgChecklistItem(organization_id=org.id, title="ICU-only item", department_id=dept.id)
    db.add(dept_item)
    db.commit()

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    body = resp.json()
    # No applicable items at all -- 0.0, not a divide-by-zero error.
    assert body[0]["checklist_completion_pct"] == 0.0


def test_mentor_name_reflects_assignment(db):
    manager = _make_user(db, "manager6@acme.com")
    org = _make_org(db)
    report = _make_user(db)
    report_app = _make_application(db, report.id, org.id, manager_email=manager.email)

    contact = models.OrgHumanContact(organization_id=org.id, name="Dana Whitfield", email="dana@acme.com", is_mentor=True)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    db.add(models.MentorAssignment(application_id=report_app.id, contact_id=contact.id))
    db.commit()

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    assert resp.json()[0]["mentor_name"] == "Dana Whitfield"


def test_mentor_name_null_when_unassigned(db):
    manager = _make_user(db, "manager7@acme.com")
    org = _make_org(db)
    report = _make_user(db)
    _make_application(db, report.id, org.id, manager_email=manager.email)

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    assert resp.json()[0]["mentor_name"] is None


def test_certification_counts_reflect_completed_and_expired(db):
    manager = _make_user(db, "manager8@acme.com")
    org = _make_org(db)
    report = _make_user(db)
    report_app = _make_application(db, report.id, org.id, manager_email=manager.email)

    req1 = models.CertificationRequirement(organization_id=org.id, name="HIPAA")
    req2 = models.CertificationRequirement(organization_id=org.id, name="Fire Safety", renewal_period_days=30)
    db.add_all([req1, req2])
    db.commit()
    db.refresh(req1)
    db.refresh(req2)

    # req1: completed, no expiration.
    db.add(models.EmployeeCertification(application_id=report_app.id, requirement_id=req1.id, completed_at=datetime.utcnow()))
    # req2: completed long ago, now expired.
    db.add(models.EmployeeCertification(
        application_id=report_app.id, requirement_id=req2.id,
        completed_at=datetime.utcnow() - timedelta(days=60), expires_at=datetime.utcnow() - timedelta(days=30),
    ))
    db.commit()

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-reports")
    body = resp.json()[0]
    assert body["certifications_total"] == 2
    assert body["certifications_completed"] == 1
    assert body["certifications_expired"] == 1
