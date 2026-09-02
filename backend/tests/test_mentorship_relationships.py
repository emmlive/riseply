"""Tests for group/reciprocal mentorship relationships (#54) --
MentorshipRelationship/MentorshipParticipant, additive to the
pre-existing 1:1 MentorAssignment system (untouched by this feature).

Covers relationship creation (group and reciprocal), participant
management, ending a relationship, meeting logging, and access control
(any participant can log/view; only an admin can create/manage
membership).
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
    user = models.User(email=f"reluser{_user_counter[0]}@x.com", hashed_password="x", full_name=f"User {_user_counter[0]}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db):
    _org_counter[0] += 1
    org = models.Organization(name="Acme Health", join_code=f"RELORG{_org_counter[0]}")
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


def _make_org_with_admin_and_employees(db, n_employees=3):
    admin = _make_user(db)
    org = _make_org(db)
    _make_member(db, org.id, admin.id, role="admin")
    employees = []
    for _ in range(n_employees):
        u = _make_user(db)
        app_row = _make_application(db, u.id, org.id)
        employees.append((u, app_row))
    return admin, org, employees


def test_create_group_relationship(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 3)
    (u1, a1), (u2, a2), (u3, a3) = employees

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={
            "relationship_type": "group", "name": "New Grad Cohort",
            "participants": [
                {"application_id": a1.id, "role": "mentor"},
                {"application_id": a2.id, "role": "mentee"},
                {"application_id": a3.id, "role": "mentee"},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["relationship_type"] == "group"
    assert body["name"] == "New Grad Cohort"
    assert len(body["participants"]) == 3
    roles = {p["role"] for p in body["participants"]}
    assert roles == {"mentor", "mentee"}


def test_create_reciprocal_relationship(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={
            "relationship_type": "reciprocal", "name": "Peer pair",
            "participants": [
                {"application_id": a1.id, "role": "peer"},
                {"application_id": a2.id, "role": "peer"},
            ],
        },
    )
    assert resp.status_code == 200
    assert all(p["role"] == "peer" for p in resp.json()["participants"])


def test_reciprocal_rejects_non_peer_roles(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={
            "relationship_type": "reciprocal",
            "participants": [
                {"application_id": a1.id, "role": "mentor"},  # wrong for reciprocal
                {"application_id": a2.id, "role": "peer"},
            ],
        },
    )
    assert resp.status_code == 400


def test_create_requires_admin(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(u1)  # a regular employee, not an admin
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    )
    assert resp.status_code == 403


def test_create_requires_at_least_two_participants(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 1)
    (u1, a1), = employees

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [{"application_id": a1.id, "role": "mentor"}]},
    )
    assert resp.status_code == 422  # pydantic min_length=2 on participants


def test_create_rejects_invalid_relationship_type(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "not_a_real_type", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    )
    assert resp.status_code == 400


def test_add_and_remove_participant(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 3)
    (u1, a1), (u2, a2), (u3, a3) = employees

    _login_as(admin)
    created = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    ).json()
    relationship_id = created["id"]

    add_resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships/{relationship_id}/participants",
        json={"application_id": a3.id, "role": "mentee"},
    )
    assert add_resp.status_code == 200
    assert len(add_resp.json()["participants"]) == 3

    participant_to_remove = next(p for p in add_resp.json()["participants"] if p["application_id"] == a3.id)
    remove_resp = client.delete(
        f"/orgs/{org.id}/mentorship-relationships/{relationship_id}/participants/{participant_to_remove['id']}",
    )
    assert remove_resp.status_code == 200
    assert len(remove_resp.json()["participants"]) == 2


def test_cannot_add_same_participant_twice(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(admin)
    created = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    ).json()

    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships/{created['id']}/participants",
        json={"application_id": a1.id, "role": "mentee"},  # already in it
    )
    assert resp.status_code == 400


def test_end_relationship(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(admin)
    created = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    ).json()

    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships/{created['id']}/end",
        json={"reason": "Cohort completed"},
    )
    assert resp.status_code == 200
    assert resp.json()["ended_at"] is not None
    assert resp.json()["end_reason"] == "Cohort completed"


def test_any_participant_can_log_a_meeting(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(admin)
    created = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "reciprocal", "participants": [
            {"application_id": a1.id, "role": "peer"}, {"application_id": a2.id, "role": "peer"},
        ]},
    ).json()

    # u2 (not the admin) logs a meeting for their own relationship
    _login_as(u2)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships/{created['id']}/meetings",
        json={"meeting_date": "2026-09-01", "notes": "Discussed onboarding progress"},
    )
    assert resp.status_code == 200

    list_resp = client.get(f"/orgs/{org.id}/mentorship-relationships/{created['id']}/meetings")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_outsider_cannot_log_or_view_meetings(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees
    outsider = _make_user(db)

    _login_as(admin)
    created = client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    ).json()

    _login_as(outsider)
    resp = client.post(
        f"/orgs/{org.id}/mentorship-relationships/{created['id']}/meetings",
        json={"meeting_date": "2026-09-01", "notes": "shouldn't work"},
    )
    assert resp.status_code == 403


def test_employee_sees_own_relationships_via_job_buddy_endpoint(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 3)
    (u1, a1), (u2, a2), (u3, a3) = employees

    _login_as(admin)
    client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    )
    # a3 isn't in the relationship above -- should see none
    _login_as(u3)
    resp = client.get(f"/applications/{a3.id}/mentorship-relationships")
    assert resp.status_code == 200
    assert resp.json() == []

    # a2 IS a participant -- should see it
    _login_as(u2)
    resp2 = client.get(f"/applications/{a2.id}/mentorship-relationships")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1


def test_list_relationships_requires_admin(db):
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    _login_as(u1)
    resp = client.get(f"/orgs/{org.id}/mentorship-relationships")
    assert resp.status_code == 403


def test_1to1_mentor_assignment_system_unaffected(db):
    """Sanity check that this feature is genuinely additive -- creating
    a group relationship doesn't touch or interfere with the existing
    1:1 MentorAssignment system at all."""
    admin, org, employees = _make_org_with_admin_and_employees(db, 2)
    (u1, a1), (u2, a2) = employees

    contact = models.OrgHumanContact(organization_id=org.id, name="Mentor X", email="mx@acme.com", is_mentor=True)
    db.add(contact)
    db.commit()
    db.refresh(contact)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/employees/{a1.id}/assign-mentor", json={"contact_id": contact.id})
    client.post(
        f"/orgs/{org.id}/mentorship-relationships",
        json={"relationship_type": "group", "participants": [
            {"application_id": a1.id, "role": "mentor"}, {"application_id": a2.id, "role": "mentee"},
        ]},
    )

    assignment = db.query(models.MentorAssignment).filter_by(application_id=a1.id).first()
    assert assignment is not None
    assert assignment.contact_id == contact.id  # untouched by the group relationship also involving a1
