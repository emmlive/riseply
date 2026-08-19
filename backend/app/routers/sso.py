"""
Enterprise SSO login flow (employee-facing), separate from admin
configuration (see routers/org_buddy.py's SSO config endpoints).

Mirrors the existing Google/Microsoft OAuth pattern (services/oauth.py)
as closely as possible for consistency, with one necessary difference:
state is stored server-side (SSOLoginState) rather than in a cookie,
since the frontend (riseply.com) and backend (a separate Render
subdomain) are different origins -- a redirect-set cookie wouldn't
reliably survive to the frontend's later POST call.

1. GET /auth/sso/{organization_id}/login -- backend redirects the
   browser directly to the org's configured IdP, with a fresh
   single-use state token.
2. The IdP redirects back to the FRONTEND's own callback page with
   ?code=...&state=...
3. The frontend POSTs {organization_id, code, state} to
   POST /auth/sso/callback -- backend verifies state, exchanges the
   code, cryptographically verifies the ID token, checks the email
   domain, finds-or-creates the user as an EMPLOYEE of this org (never
   an admin -- SSO authenticates who someone is, it should never
   itself grant elevated privileges), and returns a real Riseply
   access token in the response body. The token never touches a URL or
   browser history at any point in this flow.
"""
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app import models, schemas, security
from app.services import oidc_sso, notifier

router = APIRouter(prefix="/auth/sso", tags=["sso"])

STATE_EXPIRY_MINUTES = 10


def _redirect_uri() -> str:
    return f"{settings.oauth_frontend_base_url}/sso-callback"


@router.get("/{organization_id}/login")
def sso_login(organization_id: int, db: Session = Depends(get_db)):
    config = db.query(models.OrgSSOConfig).filter_by(organization_id=organization_id, enabled=True).first()
    if not config:
        raise HTTPException(status_code=404, detail="SSO isn't configured for this organization.")

    discovery = oidc_sso.discover(config.issuer)
    authorization_endpoint = discovery.get("authorization_endpoint")
    if not authorization_endpoint:
        raise HTTPException(status_code=502, detail="That identity provider's discovery document is missing an authorization endpoint.")

    # Single-use CSRF token, short expiry -- see SSOLoginState's own
    # docstring for why this is DB-backed rather than a cookie.
    state = secrets.token_urlsafe(32)
    db.add(models.SSOLoginState(state=state, organization_id=organization_id))
    db.commit()

    params = {
        "client_id": config.client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    return RedirectResponse(url=f"{authorization_endpoint}?{urlencode(params)}")


@router.post("/callback", response_model=schemas.TokenResponse)
def sso_callback(payload: schemas.SSOCallbackRequest, db: Session = Depends(get_db)):
    # Verify + consume the state token FIRST, before doing anything
    # else -- single-use (deleted immediately on lookup), rejects
    # anything expired or already used (replay protection). Which org
    # this callback belongs to is derived ENTIRELY from this validated
    # server-side record, never from anything the client asserts --
    # a standard OIDC redirect only reliably carries back code and
    # state anyway, so there's nothing else to trust here even if we
    # wanted to.
    state_row = db.query(models.SSOLoginState).filter_by(state=payload.state).first()
    if not state_row:
        raise HTTPException(status_code=401, detail="This sign-in link has expired or was already used — try signing in again.")
    is_expired = datetime.utcnow() - state_row.created_at > timedelta(minutes=STATE_EXPIRY_MINUTES)
    org_id = state_row.organization_id
    db.delete(state_row)
    db.commit()
    if is_expired:
        raise HTTPException(status_code=401, detail="This sign-in link has expired — try signing in again.")

    config = db.query(models.OrgSSOConfig).filter_by(organization_id=org_id, enabled=True).first()
    if not config:
        raise HTTPException(status_code=404, detail="SSO isn't configured for this organization.")

    discovery = oidc_sso.discover(config.issuer)
    token_endpoint = discovery.get("token_endpoint")
    jwks_uri = discovery.get("jwks_uri")
    if not token_endpoint or not jwks_uri:
        raise HTTPException(status_code=502, detail="That identity provider's discovery document is incomplete.")

    tokens = oidc_sso.exchange_code(token_endpoint, payload.code, config.client_id, config.client_secret, _redirect_uri())
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="That identity provider didn't return an ID token.")

    claims = oidc_sso.verify_id_token(id_token, jwks_uri, config.issuer, config.client_id)
    email = claims.get("email")
    name = claims.get("name", "")
    if not email:
        raise HTTPException(status_code=502, detail="That identity provider didn't return an email address.")

    # Real safety boundary, not just metadata -- see OrgSSOConfig's
    # docstring on allowed_email_domain.
    email_domain = email.split("@")[-1].lower()
    if email_domain != config.allowed_email_domain.lower():
        raise HTTPException(status_code=403, detail=f"This SSO connection is only for @{config.allowed_email_domain} accounts.")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(
            email=email,
            hashed_password=security.hash_password(secrets.token_urlsafe(32)),
            full_name=name,
            notify_email=email,
            tos_accepted_at=datetime.utcnow(),
            subscription_terms_accepted_at=datetime.utcnow(),
            oauth_provider="sso",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        try:
            notifier.notify_welcome(user.email, user.full_name)
        except Exception as e:
            print(f"[sso] Welcome email failed for user {user.id}: {e}")

    # Auto-provision as an EMPLOYEE of this org, same as the join-code
    # flow -- deliberately never as an admin. SSO authenticates who
    # someone is; it should never itself grant elevated privileges.
    existing_membership = db.query(models.OrganizationMember).filter_by(
        organization_id=org_id, user_id=user.id
    ).first()
    if not existing_membership:
        db.add(models.OrganizationMember(organization_id=org_id, user_id=user.id, role="employee"))
        db.commit()

    access_token = security.create_access_token(user)
    return schemas.TokenResponse(access_token=access_token)
