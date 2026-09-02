"""Microsoft Graph calendar OAuth (connect flow) and event management.

Separate from services/oauth.py on purpose: that module is login-only
-- it exchanges a code once, reads identity, and discards the token.
This module requests a DIFFERENT, broader scope (Calendars.ReadWrite
+ offline_access, on top of the same identity scopes) and persists
both the access token AND a refresh token, since calendar access needs
to keep working long after the initial connect. Same Microsoft Graph
app registration as login can serve both -- this is a second, additive
consent scope requested at a different time, not a second app.

Google Calendar isn't implemented yet -- see calendar.py's router
docstring for the phased rollout (Microsoft first, Google as a
fast-follow once this pattern is proven).
"""
from datetime import datetime, timedelta

import requests
from fastapi import HTTPException

from app.config import settings

MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# offline_access is what actually gets Microsoft to hand back a refresh
# token at all -- without it, the access token is all you get, and it
# expires in about an hour with no way to renew it short of asking the
# person to reconnect every hour, which defeats the point of "connect
# once."
CALENDAR_SCOPE = "openid email profile offline_access Calendars.ReadWrite"


def _redirect_uri() -> str:
    # A dedicated callback path, distinct from the login OAuth
    # callback (/oauth-callback/microsoft) -- Microsoft's app
    # registration needs each redirect URI it'll actually use listed
    # explicitly, so this can't silently reuse the login one even
    # though it's the same app registration.
    return f"{settings.oauth_frontend_base_url}/calendar-callback/microsoft"


def get_connect_url(state: str) -> str:
    """Returns the URL the frontend redirects the browser to for
    consent. `state` is generated and verified entirely on the
    frontend (same CSRF pattern as the existing login OAuth flow) --
    this function just needs to pass it through so Microsoft round-trips
    it back unchanged."""
    if not settings.microsoft_oauth_client_id:
        raise HTTPException(status_code=503, detail="Calendar sync isn't configured yet.")
    params = (
        f"client_id={settings.microsoft_oauth_client_id}"
        f"&response_type=code"
        f"&redirect_uri={_redirect_uri()}"
        f"&scope={CALENDAR_SCOPE.replace(' ', '%20')}"
        f"&state={state}"
        f"&response_mode=query"
    )
    return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{params}"


def exchange_code_for_tokens(code: str) -> dict:
    """Returns {"access_token", "refresh_token", "expires_at"}. Raises
    HTTPException(502) on any failure, same contract as
    services/oauth.py's exchange functions."""
    if not settings.microsoft_oauth_client_id or not settings.microsoft_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Calendar sync isn't configured yet.")

    try:
        resp = requests.post(MICROSOFT_TOKEN_URL, data={
            "code": code,
            "client_id": settings.microsoft_oauth_client_id,
            "client_secret": settings.microsoft_oauth_client_secret,
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
            "scope": CALENDAR_SCOPE,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't connect your calendar — try again.")

    if "refresh_token" not in data:
        # Shouldn't happen if offline_access was actually granted, but
        # a connection with no way to renew itself is worse than no
        # connection at all -- it would silently stop working in about
        # an hour with no path to fix it short of a full reconnect,
        # and nothing in this flow would tell the person that's what
        # happened until their next scheduling attempt just fails.
        raise HTTPException(status_code=502, detail="Microsoft didn't grant offline access — please try connecting again.")

    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
    }


def refresh_access_token(refresh_token: str) -> dict:
    """Same return shape as exchange_code_for_tokens. Microsoft may or
    may not rotate the refresh token on each use -- always store
    whatever comes back rather than assuming the old one still works,
    since a stale, no-longer-valid refresh token stored would silently
    break the NEXT refresh attempt too."""
    if not settings.microsoft_oauth_client_id or not settings.microsoft_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Calendar sync isn't configured yet.")

    try:
        resp = requests.post(MICROSOFT_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": settings.microsoft_oauth_client_id,
            "client_secret": settings.microsoft_oauth_client_secret,
            "grant_type": "refresh_token",
            "scope": CALENDAR_SCOPE,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=401, detail="This calendar connection has expired — please reconnect it.")

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),  # keep old one if not rotated
        "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
    }


def create_event(access_token: str, subject: str, start: datetime, duration_minutes: int, attendee_emails: list[str]) -> str:
    """Creates a Graph API calendar event and returns its id (used
    later for cancellation). attendee_emails are added as required
    attendees -- Microsoft's own calendar system emails them an
    invite regardless of whether THEY have anything connected to
    Riseply, same as any calendar invite works. Only one side of a
    pairing needs a CalendarConnection for both people to get a real
    invite."""
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "subject": subject,
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        "attendees": [
            {"emailAddress": {"address": email}, "type": "required"}
            for email in attendee_emails
        ],
    }
    try:
        resp = requests.post(
            f"{MICROSOFT_GRAPH_BASE}/me/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body, timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Couldn't create the calendar event: {e}")


def cancel_event(access_token: str, event_id: str) -> None:
    """Best-effort -- a 404 (event already deleted, e.g. the person
    removed it manually from their own calendar) is NOT treated as a
    failure here; the caller's goal (this event no longer exists on
    their calendar) is already satisfied either way."""
    try:
        resp = requests.delete(
            f"{MICROSOFT_GRAPH_BASE}/me/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"}, timeout=15,
        )
        if resp.status_code not in (204, 404):
            resp.raise_for_status()
    except requests.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't cancel the calendar event.")
