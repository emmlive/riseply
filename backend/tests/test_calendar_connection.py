"""Tests for calendar connection endpoints (GET /calendar/connect/{provider},
POST /calendar/callback/{provider}, GET/DELETE /calendar/connections).

Part of the October demo calendar-sync feature (#52) -- Microsoft
Graph only for now. Mocks calendar_oauth's actual network calls
throughout; these tests are about the connection lifecycle (state
generation, token storage/encryption, refresh-on-expiry, disconnect),
not about Microsoft's API itself.

Environment (DATABASE_URL, CALENDAR_TOKEN_ENCRYPTION_KEY, etc.) is set
in conftest.py, not here -- see that file for why: several test files
independently setting these via os.environ at module level meant only
whichever file pytest happened to collect FIRST actually had its
values take effect, silently, since app.config's settings singleton
is built once per process. conftest.py loads before any test module
is collected, which is what actually fixes that.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import calendar_oauth, calendar_encryption
from app.routers import calendar as calendar_router

client = TestClient(app)

_user_counter = [0]


def _make_user(db):
    _user_counter[0] += 1
    user = models.User(email=f"caluser{_user_counter[0]}@x.com", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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


def test_connect_url_requires_supported_provider(db):
    user = _make_user(db)
    _login_as(user)

    resp = client.get("/calendar/connect/google")
    assert resp.status_code == 400  # not implemented yet, see module docstring


def test_connect_url_returns_url_and_state(db):
    user = _make_user(db)
    _login_as(user)

    resp = client.get("/calendar/connect/microsoft")
    assert resp.status_code == 200
    body = resp.json()
    assert "login.microsoftonline.com" in body["url"]
    assert "Calendars.ReadWrite" in body["url"]
    assert len(body["state"]) > 10


def test_callback_stores_encrypted_tokens(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    fake_tokens = {
        "access_token": "raw-access-token-value",
        "refresh_token": "raw-refresh-token-value",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    }
    monkeypatch.setattr(calendar_oauth, "exchange_code_for_tokens", lambda code: fake_tokens)

    resp = client.post("/calendar/callback/microsoft", json={"code": "fake-auth-code"})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "microsoft"

    row = db.query(models.CalendarConnection).filter_by(user_id=user.id, provider="microsoft").first()
    assert row is not None
    # Tokens are stored encrypted, not in plaintext -- the whole point
    # of calendar_encryption.py existing.
    assert row.access_token != "raw-access-token-value"
    assert calendar_encryption.decrypt_token(row.access_token) == "raw-access-token-value"
    assert calendar_encryption.decrypt_token(row.refresh_token) == "raw-refresh-token-value"


def test_callback_reconnect_updates_existing_row_not_duplicate(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    monkeypatch.setattr(calendar_oauth, "exchange_code_for_tokens", lambda code: {
        "access_token": "first-token", "refresh_token": "first-refresh",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    })
    client.post("/calendar/callback/microsoft", json={"code": "code-1"})

    monkeypatch.setattr(calendar_oauth, "exchange_code_for_tokens", lambda code: {
        "access_token": "second-token", "refresh_token": "second-refresh",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    })
    client.post("/calendar/callback/microsoft", json={"code": "code-2"})

    rows = db.query(models.CalendarConnection).filter_by(user_id=user.id, provider="microsoft").all()
    assert len(rows) == 1
    assert calendar_encryption.decrypt_token(rows[0].access_token) == "second-token"


def test_list_connections(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    monkeypatch.setattr(calendar_oauth, "exchange_code_for_tokens", lambda code: {
        "access_token": "tok", "refresh_token": "reftok",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    })
    client.post("/calendar/callback/microsoft", json={"code": "abc"})

    resp = client.get("/calendar/connections")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["provider"] == "microsoft"
    # The list response never includes token values -- confirms the
    # schema itself can't leak them, not just that callers happen not
    # to ask for them.
    assert "access_token" not in body[0]
    assert "refresh_token" not in body[0]


def test_disconnect_removes_connection(db, monkeypatch):
    user = _make_user(db)
    _login_as(user)

    monkeypatch.setattr(calendar_oauth, "exchange_code_for_tokens", lambda code: {
        "access_token": "tok", "refresh_token": "reftok",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    })
    client.post("/calendar/callback/microsoft", json={"code": "abc"})

    resp = client.delete("/calendar/connections/microsoft")
    assert resp.status_code == 200

    remaining = db.query(models.CalendarConnection).filter_by(user_id=user.id).count()
    assert remaining == 0


def test_disconnect_404_when_nothing_connected(db):
    user = _make_user(db)
    _login_as(user)

    resp = client.delete("/calendar/connections/microsoft")
    assert resp.status_code == 404


def test_get_valid_access_token_returns_unexpired_token_directly(db):
    user = _make_user(db)
    connection = models.CalendarConnection(
        user_id=user.id, provider="microsoft",
        access_token=calendar_encryption.encrypt_token("still-valid-token"),
        refresh_token=calendar_encryption.encrypt_token("some-refresh-token"),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(connection)
    db.commit()

    with patch.object(calendar_oauth, "refresh_access_token") as mock_refresh:
        token = calendar_router.get_valid_access_token(db, connection)
    assert token == "still-valid-token"
    mock_refresh.assert_not_called()  # no refresh needed -- still valid


def test_get_valid_access_token_refreshes_when_expired(db, monkeypatch):
    user = _make_user(db)
    connection = models.CalendarConnection(
        user_id=user.id, provider="microsoft",
        access_token=calendar_encryption.encrypt_token("expired-token"),
        refresh_token=calendar_encryption.encrypt_token("valid-refresh-token"),
        expires_at=datetime.utcnow() - timedelta(minutes=5),  # already expired
    )
    db.add(connection)
    db.commit()

    monkeypatch.setattr(calendar_oauth, "refresh_access_token", lambda refresh_token: {
        "access_token": "brand-new-token",
        "refresh_token": "brand-new-refresh-token",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    })

    token = calendar_router.get_valid_access_token(db, connection)
    assert token == "brand-new-token"
    # The refreshed tokens got persisted back, re-encrypted, not just
    # returned for one-time use.
    assert calendar_encryption.decrypt_token(connection.access_token) == "brand-new-token"
    assert calendar_encryption.decrypt_token(connection.refresh_token) == "brand-new-refresh-token"
