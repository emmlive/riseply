"""Tests for the internal job board (internal mobility) --
InternalJobPosting/InternalJobApplication.

Deliberately separate from the external, AI-matched job discovery
pipeline (see InternalJobPosting's docstring) -- these tests cover
admin posting management (create, close, view applicants) and the
employee-facing browse/apply flow (only open postings, using the
resume already on file, one application per person per posting).
"""
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


def _make_user(db):
    _user_counter[0] += 1
    user = models.User(
        email=f"intjobuser{_user_counter[0]}@x.com", hashed_password="x",
        full_name=f"User {_user_counter[0]}", resume_text="Experienced professional.",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db):
    _org_counter[0] += 1
    org = models.Organization(name="Acme Health", join_code=f"INTJOB{_org_counter[0]}")
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


def _make_application(db, user_id, org_id=None, manager_email=""):
    job = _make_job(db)
    app_row = models.Application(user_id=user_id, job_id=job.id, organization_id=org_id, manager_email=manager_email)
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


def test_create_posting(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/internal-jobs",
        json={"title": "Senior ICU Nurse", "description": "Night shift, ICU unit."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Senior ICU Nurse"
    assert body["closed_at"] is None
    assert body["applicant_count"] == 0


def test_create_requires_admin(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(employee)
    resp = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Should not work"})
    assert resp.status_code == 403


def test_admin_list_includes_closed_postings(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    created = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Old Posting"}).json()
    client.post(f"/orgs/{org.id}/internal-jobs/{created['id']}/close")

    resp = client.get(f"/orgs/{org.id}/internal-jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["closed_at"] is not None


def test_employee_browse_only_shows_open_postings(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    open_posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Open Role"}).json()
    closed_posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Closed Role"}).json()
    client.post(f"/orgs/{org.id}/internal-jobs/{closed_posting['id']}/close")

    _login_as(employee)
    resp = client.get(f"/applications/{employee_app.id}/internal-jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Open Role"


def test_employee_with_no_org_sees_empty_list(db):
    unaffiliated = _make_user(db)
    unaffiliated_app = _make_application(db, unaffiliated.id, org_id=None)

    _login_as(unaffiliated)
    resp = client.get(f"/applications/{unaffiliated_app.id}/internal-jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_apply_creates_application_and_shows_has_applied(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    resp = client.post(
        f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply",
        json={"note": "I've been covering this role informally for months."},
    )
    assert resp.status_code == 200

    browse = client.get(f"/applications/{employee_app.id}/internal-jobs").json()
    assert browse[0]["has_applied"] is True


def test_matches_your_goal_reflects_career_goal_keyword_overlap(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    matching_posting = client.post(
        f"/orgs/{org.id}/internal-jobs",
        json={"title": "Senior ICU Nurse", "description": "Lead complex critical care cases."},
    ).json()
    unrelated_posting = client.post(
        f"/orgs/{org.id}/internal-jobs",
        json={"title": "Payroll Coordinator", "description": "Process biweekly payroll runs."},
    ).json()

    db.add(models.CareerGoal(application_id=employee_app.id, goal_text="Grow into an ICU leadership role"))
    db.commit()

    _login_as(employee)
    browse = client.get(f"/applications/{employee_app.id}/internal-jobs").json()
    by_title = {p["title"]: p for p in browse}
    assert by_title["Senior ICU Nurse"]["matches_your_goal"] is True
    assert by_title["Payroll Coordinator"]["matches_your_goal"] is False


def test_matches_your_goal_false_with_no_goal_set(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Senior ICU Nurse"})

    _login_as(employee)
    browse = client.get(f"/applications/{employee_app.id}/internal-jobs").json()
    assert browse[0]["matches_your_goal"] is False


def test_matches_your_goal_never_shown_on_admin_endpoint(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Senior ICU Nurse"})
    admin_view = client.get(f"/orgs/{org.id}/internal-jobs").json()
    assert admin_view[0]["matches_your_goal"] is None


def test_cannot_apply_twice(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "First"})
    resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "Second"})
    assert resp.status_code == 400


def test_cannot_apply_to_closed_posting(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    client.post(f"/orgs/{org.id}/internal-jobs/{posting['id']}/close")

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "Too late"})
    assert resp.status_code == 400


def test_admin_sees_applicants(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "Interested!"})

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["note"] == "Interested!"
    assert body[0]["applicant_email"] == employee.email

    # applicant_count on the posting itself should reflect this too
    postings = client.get(f"/orgs/{org.id}/internal-jobs").json()
    assert postings[0]["applicant_count"] == 1


def test_outsider_cannot_view_applicants(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    outsider = _make_user(db)

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(outsider)
    resp = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants")
    assert resp.status_code == 403


def test_apply_404_for_posting_in_different_org(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    other_admin, other_org, other_employee, other_employee_app = _make_org_with_admin_and_employee(db)

    _login_as(other_admin)
    other_posting = client.post(f"/orgs/{other_org.id}/internal-jobs", json={"title": "Not your org's job"}).json()

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{other_posting['id']}/apply", json={"note": "x"})
    assert resp.status_code == 404


# --- manager approval workflow ---

def test_approval_off_by_default_application_immediately_approved(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_approval_on_but_no_manager_on_file_falls_back_to_approved(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)  # no manager_email set
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    assert resp.json()["status"] == "approved"  # nowhere to route it, so no artificial blocking


def test_approval_on_with_manager_starts_pending_and_notifies_manager(db):
    from unittest.mock import patch

    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)

    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    with patch("app.routers.job_buddy.notifier.send_email") as mock_send:
        resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    assert resp.json()["status"] == "pending_approval"
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == manager.email


def test_manager_can_approve_pending_application(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()

    _login_as(employee)
    apply_resp = client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})

    _login_as(admin)
    completions = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants").json()
    application_id = completions[0]["id"]
    assert completions[0]["status"] == "pending_approval"

    _login_as(manager)
    resp = client.post(f"/orgs/{org.id}/internal-job-applications/{application_id}/decide", json={"approve": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_manager_can_decline_with_reason(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    _login_as(admin)
    application_id = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants").json()[0]["id"]

    _login_as(manager)
    resp = client.post(
        f"/orgs/{org.id}/internal-job-applications/{application_id}/decide",
        json={"approve": False, "reason": "Not enough tenure in current role yet."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"
    assert resp.json()["decline_reason"] == "Not enough tenure in current role yet."


def test_only_the_actual_manager_can_decide(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    outsider = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    _login_as(admin)
    application_id = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants").json()[0]["id"]

    _login_as(outsider)
    resp = client.post(f"/orgs/{org.id}/internal-job-applications/{application_id}/decide", json={"approve": True})
    assert resp.status_code == 403


def test_cannot_decide_an_already_decided_application(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    _login_as(admin)
    application_id = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants").json()[0]["id"]

    _login_as(manager)
    client.post(f"/orgs/{org.id}/internal-job-applications/{application_id}/decide", json={"approve": True})
    resp = client.post(f"/orgs/{org.id}/internal-job-applications/{application_id}/decide", json={"approve": False})
    assert resp.status_code == 400


def test_employee_sees_their_own_application_status(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})

    browse = client.get(f"/applications/{employee_app.id}/internal-jobs").json()
    assert browse[0]["my_application_status"] == "pending_approval"


def test_settings_partial_update_does_not_reset_approval_flag(db):
    """The real bug this schema design specifically prevents -- a
    logo-only settings save shouldn't silently turn approval back off."""
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    resp = client.put(f"/orgs/{org.id}/settings", json={"logo_url": "https://example.com/logo.png"})
    assert resp.status_code == 200
    assert resp.json()["require_manager_approval_for_internal_jobs"] is True
    assert resp.json()["logo_url"] == "https://example.com/logo.png"


def test_settings_can_explicitly_toggle_approval_flag(db):
    admin, org, employee, employee_app = _make_org_with_admin_and_employee(db)

    _login_as(admin)
    resp = client.put(f"/orgs/{org.id}/settings", json={"require_manager_approval_for_internal_jobs": True})
    assert resp.status_code == 200
    assert resp.json()["require_manager_approval_for_internal_jobs"] is True


def test_manager_can_list_their_pending_approvals(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})

    _login_as(manager)
    resp = client.get(f"/orgs/{org.id}/my-pending-approvals")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["posting_title"] == "Charge Nurse"
    assert body[0]["applicant_email"] == employee.email


def test_pending_approvals_list_excludes_already_decided(db):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    manager = _make_user(db)
    employee = _make_user(db)
    employee_app = _make_application(db, employee.id, org.id, manager_email=manager.email)
    org_row = db.query(models.Organization).filter_by(id=org.id).first()
    org_row.require_manager_approval_for_internal_jobs = True
    db.commit()

    _login_as(admin)
    posting = client.post(f"/orgs/{org.id}/internal-jobs", json={"title": "Charge Nurse"}).json()
    _login_as(employee)
    client.post(f"/applications/{employee_app.id}/internal-jobs/{posting['id']}/apply", json={"note": "x"})
    _login_as(admin)
    application_id = client.get(f"/orgs/{org.id}/internal-jobs/{posting['id']}/applicants").json()[0]["id"]

    _login_as(manager)
    client.post(f"/orgs/{org.id}/internal-job-applications/{application_id}/decide", json={"approve": True})
    resp = client.get(f"/orgs/{org.id}/my-pending-approvals")
    assert resp.json() == []

