"""
Cloudflare Turnstile verification. Gracefully degrades: if
TURNSTILE_SECRET_KEY isn't configured, verification is skipped entirely
(returns True) rather than blocking signups -- same pattern as Stripe
and every other optional integration in this app. Set the key to
actually require a passing CAPTCHA.
"""
import requests

from app.config import settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token: str, remote_ip: str = "") -> bool:
    if not settings.turnstile_secret_key:
        return True  # not configured -- don't block signups over it

    if not token:
        return False  # configured AND required, but no token was provided

    try:
        resp = requests.post(
            VERIFY_URL,
            data={
                "secret": settings.turnstile_secret_key,
                "response": token,
                "remoteip": remote_ip,
            },
            timeout=10,
        )
        return bool(resp.json().get("success"))
    except Exception:
        # If Cloudflare's verification service itself is unreachable,
        # fail closed (reject) rather than silently letting bots through --
        # this is the one place "degrade gracefully" would defeat the
        # entire point of having a CAPTCHA.
        return False
