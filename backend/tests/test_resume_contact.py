import uuid

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import resume_contact

RESUME = "Emmanuel Ogunyinka, M.S., CISA\nemmanuel.ogunyinka@yahoo.com | (240) 601-3875 | Plainfield, IL\n\nEXPERIENCE\nWrote to old@example.com about 202-555-0100."


def test_first_email_and_phone_in_the_header_are_used():
    assert resume_contact.extract(RESUME) == {"email": "emmanuel.ogunyinka@yahoo.com", "phone": "(240) 601-3875"}


def test_nothing_found_gives_empty_strings():
    assert resume_contact.extract("No contact here") == {"email": "", "phone": ""}
    assert resume_contact.extract("") == {"email": "", "phone": ""}


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"acct-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", full_name="Jane Doe",
                       phone="111", resume_text="")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_candidate_uses_the_resume_email_not_the_account_email(ctx):
    db, user, c = ctx
    user.resume_text = RESUME; db.commit()
    body = c.get("/extension/candidate").json()
    assert body["email"] == "emmanuel.ogunyinka@yahoo.com" and body["email_source"] == "resume"
    assert body["phone"] == "(240) 601-3875" and body["full_name"] == "Jane Doe"


def test_candidate_falls_back_to_the_account_when_the_resume_has_no_email(ctx):
    db, user, c = ctx
    user.resume_text = "Just words"; db.commit()
    body = c.get("/extension/candidate").json()
    assert body["email"] == user.email and body["email_source"] == "profile" and body["phone"] == "111"
