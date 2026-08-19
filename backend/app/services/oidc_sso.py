"""
OIDC (OpenID Connect) discovery, code exchange, and ID token
verification for enterprise SSO.

The single most security-critical function here is verify_id_token --
it's what stands between "an employee actually authenticated with
their company's real identity provider" and "anyone who can construct
a JSON blob claiming to be a valid token." Verification is delegated
entirely to python-jose (already a trusted dependency in this codebase
for the app's own JWT auth), which correctly checks the cryptographic
signature against the provider's published public keys, the audience,
the issuer, and expiry -- never hand-rolled.
"""
import requests
from fastapi import HTTPException
from jose import jwt as jose_jwt
from jose.exceptions import JOSEError

_DISCOVERY_TIMEOUT = 10
_TOKEN_EXCHANGE_TIMEOUT = 15
_JWKS_TIMEOUT = 10


def discover(issuer: str) -> dict:
    """Fetches the provider's .well-known/openid-configuration document
    -- standard for any OIDC-compliant provider, so the org admin only
    has to give us the issuer URL, not four separate endpoint URLs by
    hand."""
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = requests.get(url, timeout=_DISCOVERY_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't reach that identity provider's discovery endpoint — check the issuer URL.")


def exchange_code(token_endpoint: str, code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    """Returns the raw token response (includes id_token, access_token).
    Client secret only ever travels server-to-server here, same
    principle as the existing Google/Microsoft OAuth service."""
    try:
        resp = requests.post(token_endpoint, data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }, timeout=_TOKEN_EXCHANGE_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't complete sign-in with that identity provider — try again.")


def verify_id_token(id_token: str, jwks_uri: str, issuer: str, client_id: str) -> dict:
    """Fetches the provider's current public keys and cryptographically
    verifies the ID token's signature, audience, issuer, and expiry.
    Raises HTTPException(401) on ANY verification failure -- a failed
    verification must never be treated as "probably fine," since that's
    exactly the class of bug that turns into an authentication bypass.
    Returns the verified claims dict only on success."""
    try:
        jwks_resp = requests.get(jwks_uri, timeout=_JWKS_TIMEOUT)
        jwks_resp.raise_for_status()
        jwks = jwks_resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't fetch the identity provider's signing keys.")

    try:
        claims = jose_jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
        )
    except JOSEError as e:
        # Deliberately generic to the caller -- an attacker probing for
        # exactly which check failed (bad signature vs. wrong audience
        # vs. expired) shouldn't get that for free. The real reason is
        # still logged server-side for legitimate debugging.
        print(f"[oidc_sso] ID token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Couldn't verify your identity provider's response.")

    return claims
