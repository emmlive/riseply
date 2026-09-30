"""Tests for the coaching (practical, role-specific training) endpoints
added under /applications/{id}/coaching/sessions.

app.services.coaching's Claude-calling functions are monkeypatched
throughout, same pattern as test_handoff_requests.py mocking
notifier.send_email -- these tests are about the endpoints' access
control, state machine (in_progress -> completed), and usage metering,
not about real LLM output.
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


def _make_user(db, resume_text="Experienced nurse, 5 years ICU."):
    _user_counter[0] += 1
    user = models.User(
        email=f"coachuser{_user_counter[0]}@x.com", hashed_password="x",
        full_name="Test User", resume_text=resume_text,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_job(db):
    import uuid
    job = models.Job(source="test", external_id=uuid.uuid4().hex, company="Acme Health", title="ICU Nurse", location="Remote", description="Bedside ICU care.")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _make_application(db, user_id, org_id=None):
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


def _start_session(db, user, app_row, session_type="drill", topic="", result=None):
    result = result or {"topic": "Triage judgment", "opening_message": "What do you do first?"}
    _login_as(user)
    with patch("app.routers.job_buddy.coaching_service.start_coaching_session", return_value=result):
        return client.post(
            f"/applications/{app_row.id}/coaching/sessions",
            json={"session_type": session_type, "topic": topic},
        )


def test_start_session_requires_resume(db):
    user = _make_user(db, resume_text="")
    app_row = _make_application(db, user.id)

    resp = _start_session(db, user, app_row)
    assert resp.status_code == 400
    assert "resume" in resp.json()["detail"].lower()


def test_start_session_creates_session_and_opening_message(db):
    user = _make_user(db)
    app_row = _make_application(db, user.id)

    resp = _start_session(db, user, app_row, session_type="roleplay", topic="Angry family member")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["session_type"] == "roleplay"
    assert body["session"]["status"] == "in_progress"
    assert body["session"]["topic"] == "Triage judgment"  # from the mocked result
    assert body["opening_message"]["role"] == "assistant"
    assert body["opening_message"]["content"] == "What do you do first?"

    # Persisted for real, not just returned -- both the session row and
    # its opening message should be queryable afterward.
    sessions = db.query(models.CoachingSession).filter_by(application_id=app_row.id).all()
    assert len(sessions) == 1
    messages = db.query(models.CoachingMessage).filter_by(session_id=sessions[0].id).all()
    assert len(messages) == 1


def test_start_session_404_for_someone_elses_application(db):
    owner = _make_user(db)
    outsider = _make_user(db)
    app_row = _make_application(db, owner.id)

    resp = _start_session(db, outsider, app_row)
    assert resp.status_code == 404


def test_start_session_failure_does_not_count_against_usage(db):
    user = _make_user(db)
    app_row = _make_application(db, user.id)

    _login_as(user)
    with patch("app.routers.job_buddy.coaching_service.start_coaching_session", side_effect=RuntimeError("boom")):
        resp = client.post(
            f"/applications/{app_row.id}/coaching/sessions",
            json={"session_type": "drill", "topic": ""},
        )
    assert resp.status_code == 502

    from app.services import usage
    assert usage.get_usage(db, user.id, "coaching_message") == 0


def test_send_message_appends_to_transcript_and_requires_in_progress(db):
    user = _make_user(db)
    app_row = _make_application(db, user.id)
    start_resp = _start_session(db, user, app_row)
    session_id = start_resp.json()["session"]["id"]

    _login_as(user)
    with patch("app.routers.job_buddy.coaching_service.coaching_reply", return_value="Good instinct -- what's next?"):
        resp = client.post(
            f"/applications/{app_row.id}/coaching/sessions/{session_id}/messages",
            json={"message": "I'd check the airway first."},
        )
    assert resp.status_code == 200
    assert resp.json()["content"] == "Good instinct -- what's next?"

    messages = db.query(models.CoachingMessage).filter_by(session_id=session_id).order_by(models.CoachingMessage.created_at).all()
    assert len(messages) == 3  # opening + user reply + coach reply
    assert messages[1].role == "user"
    assert messages[2].role == "assistant"

    # Complete it, then sending another message should be rejected.
    with patch("app.routers.job_buddy.coaching_service.finish_coaching_session", return_value={"score": 80, "feedback": "Solid."}):
        complete_resp = client.post(f"/applications/{app_row.id}/coaching/sessions/{session_id}/complete")
    assert complete_resp.status_code == 200

    resp = client.post(
        f"/applications/{app_row.id}/coaching/sessions/{session_id}/messages",
        json={"message": "one more thing"},
    )
    assert resp.status_code == 400


def test_complete_session_sets_score_and_feedback(db):
    user = _make_user(db)
    app_row = _make_application(db, user.id)
    start_resp = _start_session(db, user, app_row)
    session_id = start_resp.json()["session"]["id"]

    _login_as(user)
    with patch("app.routers.job_buddy.coaching_service.coaching_reply", return_value="Nice."):
        client.post(
            f"/applications/{app_row.id}/coaching/sessions/{session_id}/messages",
            json={"message": "my answer"},
        )

    with patch("app.routers.job_buddy.coaching_service.finish_coaching_session", return_value={"score": 92, "feedback": "Handled it well overall."}):
        resp = client.post(f"/applications/{app_row.id}/coaching/sessions/{session_id}/complete")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["score"] == 92
    assert body["feedback"] == "Handled it well overall."
    assert body["completed_at"] is not None


def test_complete_session_requires_at_least_one_exchange(db):
    user = _make_user(db)
    app_row = _make_application(db, user.id)
    start_resp = _start_session(db, user, app_row)
    session_id = start_resp.json()["session"]["id"]

    _login_as(user)
    resp = client.post(f"/applications/{app_row.id}/coaching/sessions/{session_id}/complete")
    assert resp.status_code == 400


def test_list_sessions_scoped_to_owner_and_application(db):
    user = _make_user(db)
    other_user = _make_user(db)
    app_row = _make_application(db, user.id)
    _start_session(db, user, app_row, topic="First")

    _login_as(other_user)
    resp = client.get(f"/applications/{app_row.id}/coaching/sessions")
    assert resp.status_code == 404  # other_user doesn't own this application

    _login_as(user)
    resp = client.get(f"/applications/{app_row.id}/coaching/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_admin_accounts_are_not_metered_for_coaching(db):
    user = _make_user(db)
    user.is_admin = True
    db.commit()
    app_row = _make_application(db, user.id)

    resp = _start_session(db, user, app_row)
    assert resp.status_code == 200

    from app.services import usage
    assert usage.get_usage(db, user.id, "coaching_message") == 0
