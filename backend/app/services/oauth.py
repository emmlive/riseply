"""
Server-side OAuth code exchange for Google and Microsoft sign-in.
Client secrets live only here -- the frontend only ever handles the
client ID (not secret) and the authorization code, never the secret or
the resulting access token from the provider.
"""
import requests
from fastapi import HTTPException

from app.config import settings

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"


def _redirect_uri(provider: str) -> str:
    return f"{settings.oauth_frontend_base_url}/oauth-callback/{provider}"


def exchange_google_code(code: str) -> dict:
    """Returns {"email": ..., "name": ...}. Raises HTTPException(502) on
    any failure -- network issue, invalid/expired code, provider outage
    -- so the caller always gets a clean error rather than a raw crash."""
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in isn't configured yet.")

    try:
        token_resp = requests.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": _redirect_uri("google"),
            "grant_type": "authorization_code",
        }, timeout=15)
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        userinfo_resp = requests.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15
        )
        userinfo_resp.raise_for_status()
        data = userinfo_resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't complete Google sign-in — try again.")

    email = data.get("email")
    if not email:
        raise HTTPException(status_code=502, detail="Google didn't return an email address for this account.")
    return {"email": email, "name": data.get("name", "")}


def exchange_microsoft_code(code: str) -> dict:
    """Same contract as exchange_google_code. Microsoft Graph's /me can
    return the email under either 'mail' or 'userPrincipalName' depending
    on account type (personal vs. work/school) -- checks both."""
    if not settings.microsoft_oauth_client_id or not settings.microsoft_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Microsoft sign-in isn't configured yet.")

    try:
        token_resp = requests.post(MICROSOFT_TOKEN_URL, data={
            "code": code,
            "client_id": settings.microsoft_oauth_client_id,
            "client_secret": settings.microsoft_oauth_client_secret,
            "redirect_uri": _redirect_uri("microsoft"),
            "grant_type": "authorization_code",
            "scope": "openid email profile User.Read",
        }, timeout=15)
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        userinfo_resp = requests.get(
            MICROSOFT_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15
        )
        userinfo_resp.raise_for_status()
        data = userinfo_resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't complete Microsoft sign-in — try again.")

    email = data.get("mail") or data.get("userPrincipalName")
    if not email:
        raise HTTPException(status_code=502, detail="Microsoft didn't return an email address for this account.")
    return {"email": email, "name": data.get("displayName", "")}
