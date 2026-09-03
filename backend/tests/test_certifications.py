"""Tests for compliance certifications -- CertificationRequirement/
EmployeeCertification.

Deliberately separate from the onboarding checklist system (see
CertificationRequirement's own docstring) -- these tests cover admin
requirement management, department-vs-company-wide scoping (same
layering pattern as onboarding content), the employee self-attestation
flow, the completed/expired status computation, the renewal-creates-a-
new-record behavior, and the admin verification step being genuinely
separate from completion.
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
_dept_counter = [0]
_job_counter = [0]


def _make_user(db):
    _user_counter[0] += 1
    user = models.User(email=f"certuser{_user_counter[0]}@x.com", hashed_password="x", full_name=f"User {_user_counter[0]}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db):
    _org_counter[0] += 1
    org = models.Organization(name="Acme Health", join_code=f"CERTORG{_org_counter[0]}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_department(db, org_id, name="Nursing"):
    _dept_counter[0] += 1
    dept = models.Department(organization_id=org_id, name=name, join_code=f"CERTDEPT{_dept_counter[0]}")
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


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


def _make_application(db, user_id, org_id=None, department_id=None):
    job = _make_job(db)
    app_row = models.Application(user_id=user_id, job_id=job.id, organization_id=org_id, department_id=department_id)
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


def test_create_requirement(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/certification-requirements",
        json={"name": "HIPAA Training", "description": "Annual privacy training", "renewal_period_days": 365},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "HIPAA Training"
    assert body["renewal_period_days"] == 365
    assert body["my_status"] is None  # admin endpoint, no single employee context


def test_create_requires_admin(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(employee)
    resp = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Should not work"})
    assert resp.status_code == 403


def test_employee_sees_not_started_before_completing(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Fire Safety"})

    _login_as(employee)
    resp = client.get(f"/applications/{employee_app.id}/certifications")
    assert resp.status_code == 200
    assert resp.json()[0]["my_status"] == "not_started"


def test_employee_can_self_attest_completion(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Fire Safety"}).json()

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")
    assert resp.status_code == 200
    assert resp.json()["my_status"] == "completed"
    assert resp.json()["my_verified"] is False  # self-attested, not yet admin-verified

    browse = client.get(f"/applications/{employee_app.id}/certifications").json()
    assert browse[0]["my_status"] == "completed"


def test_no_renewal_period_means_no_expiration(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "One-time Orientation"}).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")
    resp = client.get(f"/applications/{employee_app.id}/certifications").json()
    assert resp[0]["my_expires_at"] is None
    assert resp[0]["my_status"] == "completed"


def test_expired_status_reflects_past_expiration_date(db):
    """Directly manipulates completed_at/expires_at to simulate time
    passing, rather than waiting -- confirms the expired/not-expired
    boundary is computed correctly."""
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req_resp = client.post(
        f"/orgs/{org.id}/certification-requirements",
        json={"name": "Annual Cert", "renewal_period_days": 30},
    ).json()
    requirement = db.query(models.CertificationRequirement).filter_by(id=req_resp["id"]).first()

    # Simulate a completion that happened long enough ago to have expired.
    old_completion = models.EmployeeCertification(
        application_id=employee_app.id, requirement_id=requirement.id,
        completed_at=datetime.utcnow() - timedelta(days=60),
        expires_at=datetime.utcnow() - timedelta(days=30),
    )
    db.add(old_completion)
    db.commit()

    _login_as(employee)
    resp = client.get(f"/applications/{employee_app.id}/certifications").json()
    assert resp[0]["my_status"] == "expired"


def test_renewal_creates_new_record_not_update(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(
        f"/orgs/{org.id}/certification-requirements",
        json={"name": "Annual Cert", "renewal_period_days": 30},
    ).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")

    count = db.query(models.EmployeeCertification).filter_by(
        application_id=employee_app.id, requirement_id=req["id"],
    ).count()
    assert count == 2  # two genuinely separate completion records, not one updated in place


def test_department_scoped_requirement_only_shows_for_that_department(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    dept = _make_department(db, org.id, "ICU")
    icu_employee = _make_user(db)
    icu_app = _make_application(db, icu_employee.id, org.id, department_id=dept.id)

    _login_as(admin)
    client.post(
        f"/orgs/{org.id}/certification-requirements",
        json={"name": "ICU-specific Cert", "department_id": dept.id},
    )

    # The company-wide employee (no department) shouldn't see it
    _login_as(employee)
    general_view = client.get(f"/applications/{employee_app.id}/certifications").json()
    assert general_view == []

    # The ICU employee should
    _login_as(icu_employee)
    icu_view = client.get(f"/applications/{icu_app.id}/certifications").json()
    assert len(icu_view) == 1
    assert icu_view[0]["name"] == "ICU-specific Cert"


def test_company_wide_requirement_shows_for_everyone(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    dept = _make_department(db, org.id, "Radiology")
    dept_employee = _make_user(db)
    dept_app = _make_application(db, dept_employee.id, org.id, department_id=dept.id)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Code of Conduct"})

    _login_as(employee)
    assert len(client.get(f"/applications/{employee_app.id}/certifications").json()) == 1

    _login_as(dept_employee)
    assert len(client.get(f"/applications/{dept_app.id}/certifications").json()) == 1


def test_admin_sees_full_completion_history(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Fire Safety"}).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/certification-requirements/{req['id']}/completions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["applicant_email"] == employee.email
    assert body[0]["verified_at"] is None


def test_admin_can_verify_a_completion(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Fire Safety"}).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")

    _login_as(admin)
    completions = client.get(f"/orgs/{org.id}/certification-requirements/{req['id']}/completions").json()
    completion_id = completions[0]["id"]

    resp = client.post(f"/orgs/{org.id}/employee-certifications/{completion_id}/verify")
    assert resp.status_code == 200
    assert resp.json()["verified_by_user_id"] == admin.id
    assert resp.json()["verified_at"] is not None

    _login_as(employee)
    browse = client.get(f"/applications/{employee_app.id}/certifications").json()
    assert browse[0]["my_verified"] is True


def test_outsider_cannot_verify_completions(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    outsider = _make_user(db)

    _login_as(admin)
    req = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Fire Safety"}).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")

    _login_as(admin)
    completions = client.get(f"/orgs/{org.id}/certification-requirements/{req['id']}/completions").json()
    completion_id = completions[0]["id"]

    _login_as(outsider)
    resp = client.post(f"/orgs/{org.id}/employee-certifications/{completion_id}/verify")
    assert resp.status_code == 403


def test_delete_requirement(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(f"/orgs/{org.id}/certification-requirements", json={"name": "Old Requirement"}).json()
    resp = client.delete(f"/orgs/{org.id}/certification-requirements/{req['id']}")
    assert resp.status_code == 200

    remaining = client.get(f"/orgs/{org.id}/certification-requirements").json()
    assert remaining == []


def test_content_snapshot_captured_at_completion_time(db):
    """The compliance-critical part -- if the requirement's content
    changes later, an already-completed record still shows exactly
    what was acknowledged at the time, same discipline as
    ChecklistCompletion.policy_content_snapshot."""
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    req = client.post(
        f"/orgs/{org.id}/certification-requirements",
        json={"name": "Code of Ethics", "content": "Original policy text version 1."},
    ).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/certifications/{req['id']}/complete")

    # Admin edits the requirement's content after the fact -- directly
    # via the model, since there's no PATCH endpoint for this in scope.
    requirement = db.query(models.CertificationRequirement).filter_by(id=req["id"]).first()
    requirement.content = "Updated policy text version 2."
    db.commit()

    completion = db.query(models.EmployeeCertification).filter_by(application_id=employee_app.id, requirement_id=req["id"]).first()
    assert completion.content_snapshot == "Original policy text version 1."


def test_cannot_complete_requirement_from_different_org(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    other_admin, other_org, other_employee, other_employee_app = _make_org_with_admin_and_employee(db)

    _login_as(other_admin)
    other_req = client.post(f"/orgs/{other_org.id}/certification-requirements", json={"name": "Not your org's cert"}).json()

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/certifications/{other_req['id']}/complete")
    assert resp.status_code == 404


# --- certification_reminders.py ---

def test_reminder_sent_for_expiring_certification(db):
    from unittest.mock import patch
    from app.services import certification_reminders

    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    requirement = models.CertificationRequirement(organization_id=org.id, name="Annual Cert", renewal_period_days=365)
    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    # Expires in 10 days -- within the 30-day reminder window.
    cert = models.EmployeeCertification(
        application_id=employee_app.id, requirement_id=requirement.id,
        completed_at=datetime.utcnow() - timedelta(days=355),
        expires_at=datetime.utcnow() + timedelta(days=10),
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)

    with patch("app.services.notifier.send_email") as mock_send:
        certification_reminders.run_certification_reminders(db)

    db.refresh(cert)
    assert cert.reminder_last_sent_at is not None
    sent_to = {call.args[0] for call in mock_send.call_args_list}
    assert employee.email in sent_to


def test_no_reminder_for_certification_not_yet_near_expiry(db):
    from unittest.mock import patch
    from app.services import certification_reminders

    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    requirement = models.CertificationRequirement(organization_id=org.id, name="Annual Cert", renewal_period_days=365)
    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    # Expires in 200 days -- well outside the 30-day reminder window.
    cert = models.EmployeeCertification(
        application_id=employee_app.id, requirement_id=requirement.id,
        completed_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=200),
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)

    with patch("app.services.notifier.send_email") as mock_send:
        certification_reminders.run_certification_reminders(db)

    db.refresh(cert)
    assert cert.reminder_last_sent_at is None
    sent_to = {call.args[0] for call in mock_send.call_args_list}
    assert employee.email not in sent_to


def test_reminder_guard_only_checks_latest_completion_per_pair(db):
    """A stale, already-superseded completion record from before a
    renewal shouldn't trigger a reminder just because it still exists
    in history -- only the MOST RECENT completion for a given
    (application, requirement) pair should be considered."""
    from unittest.mock import patch
    from app.services import certification_reminders

    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    requirement = models.CertificationRequirement(organization_id=org.id, name="Annual Cert", renewal_period_days=365)
    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    # Old, already-expired completion (superseded by a renewal below).
    old_cert = models.EmployeeCertification(
        application_id=employee_app.id, requirement_id=requirement.id,
        completed_at=datetime.utcnow() - timedelta(days=400),
        expires_at=datetime.utcnow() - timedelta(days=35),
    )
    db.add(old_cert)
    db.commit()

    # Fresh renewal -- expires far in the future, well outside the reminder window.
    new_cert = models.EmployeeCertification(
        application_id=employee_app.id, requirement_id=requirement.id,
        completed_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
    )
    db.add(new_cert)
    db.commit()
    db.refresh(new_cert)

    with patch("app.services.notifier.send_email") as mock_send:
        certification_reminders.run_certification_reminders(db)

    db.refresh(new_cert)
    assert new_cert.reminder_last_sent_at is None  # not due -- expires in a year
    sent_to = {call.args[0] for call in mock_send.call_args_list}
    assert employee.email not in sent_to
