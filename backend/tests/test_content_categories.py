"""Tests for org content categories (added to close two RFI gaps:
wellbeing resources and mentoring-specific resource organization).

Reuses the same module-level DATABASE_URL/CRON_SECRET setup and
get_current_user override pattern as test_mentorship.py -- kept in a
separate file since this is a distinct feature area (content library,
not mentorship specifically), even though the underlying app/db setup
is identical.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models

client = TestClient(app)


def _make_user(db, email):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db, name="Acme Health"):
    org = models.Organization(name=name, join_code=f"CODE{name[:4].upper()}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_member(db, org_id, user_id, role="admin", department_id=None):
    member = models.OrganizationMember(organization_id=org_id, user_id=user_id, role=role, department_id=department_id)
    db.add(member)
    db.commit()
    return member


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


def test_categories_endpoint_returns_expected_list():
    resp = client.get("/orgs/content/categories")
    assert resp.status_code == 200
    body = resp.json()
    assert "General" in body
    assert "Mentoring Resource" in body
    assert "Wellbeing" in body


def test_add_content_defaults_to_general_category(db):
    admin = _make_user(db, "cadmin1@acme.com")
    org = _make_org(db, "OrgX")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.post(f"/orgs/{org.id}/content", json={"title": "Handbook", "content": "Some content"})
    assert resp.status_code == 200
    assert resp.json()["category"] == "General"


def test_add_content_with_specific_category(db):
    admin = _make_user(db, "cadmin2@acme.com")
    org = _make_org(db, "OrgY")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/content",
        json={"title": "Stress management guide", "content": "Some content", "category": "Wellbeing"},
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "Wellbeing"


def test_add_content_rejects_invalid_category(db):
    admin = _make_user(db, "cadmin3@acme.com")
    org = _make_org(db, "OrgZ")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/content",
        json={"title": "Handbook", "content": "Some content", "category": "Not A Real Category"},
    )
    assert resp.status_code == 400


def test_list_content_includes_category(db):
    admin = _make_user(db, "cadmin4@acme.com")
    org = _make_org(db, "Zenith Health")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    client.post(
        f"/orgs/{org.id}/content",
        json={"title": "Mentor guide", "content": "Some content", "category": "Mentoring Resource"},
    )
    resp = client.get(f"/orgs/{org.id}/content")
    assert resp.status_code == 200
    assert resp.json()[0]["category"] == "Mentoring Resource"
