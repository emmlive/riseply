"""Field-level encryption for calendar OAuth tokens.

This is the first place in the codebase doing encryption at the field
level rather than relying on infrastructure-level encryption (Postgres/
Neon at rest, TLS in transit) the way everything else does -- a
deliberate exception, not an oversight. Access and refresh tokens are
real, reusable credentials to someone's actual calendar; a database
backup, an accidental log line, or a misconfigured read replica
exposing them in plaintext is a meaningfully worse outcome than the
same exposure for, say, a cached job title.

Uses Fernet (symmetric, authenticated encryption from the `cryptography`
library, already a transitive dependency via python-jose[cryptography]
-- now explicit in requirements.txt rather than relying on that staying
true) rather than anything homegrown. Fernet also refuses to decrypt
anything that's been tampered with (it's authenticated, not just
encrypted), which matters here: a corrupted or tampered token should
fail loudly, not silently decrypt into garbage that gets sent to
Microsoft/Google as a bearer token.
"""
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings


def _get_fernet() -> Fernet:
    if not settings.calendar_token_encryption_key:
        # Fails loudly and early rather than silently storing tokens in
        # plaintext if this setting is ever left unset -- calendar sync
        # simply doesn't work at all without it, which is the correct
        # failure mode (never trade "it works" for "it works, unencrypted").
        raise HTTPException(status_code=503, detail="Calendar sync isn't configured (CALENDAR_TOKEN_ENCRYPTION_KEY unset).")
    return Fernet(settings.calendar_token_encryption_key.encode("utf-8"))


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # A tampered, corrupted, or encrypted-under-a-different-key
        # value -- e.g. CALENDAR_TOKEN_ENCRYPTION_KEY got rotated
        # without re-encrypting existing rows. Surface as a clear 401
        # from Microsoft/Google's perspective (the caller should treat
        # this the same as an expired/invalid token and prompt a
        # reconnect) rather than crashing with a raw crypto exception.
        raise HTTPException(status_code=401, detail="This calendar connection is no longer valid -- please reconnect it.")
