from datetime import datetime, timedelta
import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    # bcrypt has a hard 72-byte input limit; truncate defensively so overly
    # long passwords don't raise instead of just being capped.
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw_bytes = plain.encode("utf-8")[:72]
    return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))


def create_access_token(user: "models.User") -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "tv": user.token_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        token_version = payload.get("tv")
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_error
    # A token issued before a password reset carries the old token_version
    # and must be rejected -- this is what actually logs out every other
    # session when a user resets their password.
    if token_version is not None and token_version != user.token_version:
        raise credentials_error
    if user.is_suspended:
        # Cuts off an already-issued token immediately, not just future
        # logins -- a suspension should take effect right away, not the
        # next time the person happens to log back in.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended. Contact support if you believe this is a mistake.",
        )
    return user


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


# --- Role-based admin access ---
#
# admin_role scopes what an admin account can do. "super" (including the
# legacy empty-string role backfilled to "super" by migrate.py) can do
# everything, including managing other admins. Every other role is
# limited to a fixed set of categories; "readonly" can view any category
# but never perform a mutating action, regardless of which categories it
# would otherwise match.
ROLE_CATEGORIES: dict[str, set[str]] = {
    "support": {"users", "support", "moderation"},
    "billing": {"billing"},
    "readonly": set(),  # handled specially: view-only, everything
}


def _effective_role(user: models.User) -> str:
    return user.admin_role or "super"


def require_admin_view(*categories: str):
    """At least one of `categories` must be visible to this admin's role.
    super and readonly can view any category."""
    def dependency(user: models.User = Depends(get_current_admin)) -> models.User:
        role = _effective_role(user)
        if role in ("super", "readonly"):
            return user
        allowed = ROLE_CATEGORIES.get(role, set())
        if allowed.intersection(categories):
            return user
        raise HTTPException(status_code=403, detail="Your admin role doesn't include this section.")
    return dependency


def require_admin_action(*categories: str):
    """At least one of `categories` must be actionable by this admin's
    role. super can do anything; readonly can never perform an action,
    even in a category it can view."""
    def dependency(user: models.User = Depends(get_current_admin)) -> models.User:
        role = _effective_role(user)
        if role == "super":
            return user
        if role == "readonly":
            raise HTTPException(status_code=403, detail="Read-only admins can't perform actions.")
        allowed = ROLE_CATEGORIES.get(role, set())
        if allowed.intersection(categories):
            return user
        raise HTTPException(status_code=403, detail="Your admin role doesn't include this action.")
    return dependency


def get_current_super_admin(user: models.User = Depends(get_current_admin)) -> models.User:
    if _effective_role(user) != "super":
        raise HTTPException(status_code=403, detail="Only super admins can manage other admins.")
    return user
