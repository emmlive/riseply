from datetime import datetime, timedelta
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.rate_limit import limiter, get_real_client_ip
from app import models, schemas, security
from app.services import notifier, captcha, oauth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.TokenResponse)
@limiter.limit("5/hour")
def signup(request: Request, payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    if not payload.agree_to_terms:
        raise HTTPException(
            status_code=400,
            detail="You need to agree to the Terms of Service and Privacy Policy to create an account.",
        )

    if not payload.agree_to_subscription_terms:
        raise HTTPException(
            status_code=400,
            detail="You need to agree to the Subscription Agreement to create an account.",
        )

    if not captcha.verify_turnstile(payload.captcha_token, get_real_client_ip(request)):
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed — please try again.")

    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = models.User(
        email=payload.email,
        hashed_password=security.hash_password(payload.password),
        full_name=payload.full_name,
        notify_email=payload.email,
        tos_accepted_at=datetime.utcnow(),
        subscription_terms_accepted_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        notifier.notify_welcome(user.email, user.full_name)
    except Exception:
        pass  # welcome email is a nice-to-have -- never block signup on it

    token = security.create_access_token(user)
    return schemas.TokenResponse(access_token=token)


@router.post("/login", response_model=schemas.TokenResponse)
@limiter.limit("15/hour")
def login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not security.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = security.create_access_token(user)
    return schemas.TokenResponse(access_token=token)


def _find_or_create_oauth_user(db: Session, email: str, name: str, provider: str) -> models.User:
    """Links by email -- an OAuth sign-in with an email that already has
    a password-based account signs them into that same account rather
    than creating a duplicate. A brand-new account gets a random,
    unguessable password hash (not a nullable password column) --
    minimal-blast-radius choice that keeps the existing password-login
    code path completely untouched; if they later want password access,
    the existing 'forgot password' flow already handles setting a real
    one for any account."""
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return user

    user = models.User(
        email=email,
        hashed_password=security.hash_password(secrets.token_urlsafe(32)),
        full_name=name,
        notify_email=email,
        tos_accepted_at=datetime.utcnow(),
        subscription_terms_accepted_at=datetime.utcnow(),
        oauth_provider=provider,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        notifier.notify_welcome(user.email, user.full_name)
    except Exception:
        pass
    return user


@router.post("/oauth/google/callback", response_model=schemas.TokenResponse)
@limiter.limit("10/hour")
def google_oauth_callback(request: Request, payload: schemas.OAuthCallbackRequest, db: Session = Depends(get_db)):
    info = oauth.exchange_google_code(payload.code)
    user = _find_or_create_oauth_user(db, info["email"], info["name"], "google")
    token = security.create_access_token(user)
    return schemas.TokenResponse(access_token=token)


@router.post("/oauth/microsoft/callback", response_model=schemas.TokenResponse)
@limiter.limit("10/hour")
def microsoft_oauth_callback(request: Request, payload: schemas.OAuthCallbackRequest, db: Session = Depends(get_db)):
    info = oauth.exchange_microsoft_code(payload.code)
    user = _find_or_create_oauth_user(db, info["email"], info["name"], "microsoft")
    token = security.create_access_token(user)
    return schemas.TokenResponse(access_token=token)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@router.post("/forgot-password")
@limiter.limit("5/hour")
def forgot_password(request: Request, payload: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Always returns the same generic response whether or not the email
    is registered -- revealing that would let anyone probe for which
    emails have Riseply accounts (account enumeration). Rate-limited
    separately from the enumeration protection: without a limit, someone
    could email-bomb an arbitrary inbox by repeatedly requesting resets
    for an address they don't own."""
    generic_response = {
        "message": "If an account exists for that email, we've sent a password reset link."
    }

    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        return generic_response

    raw_token = secrets.token_urlsafe(32)
    reset_row = models.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=settings.password_reset_expire_minutes),
    )
    db.add(reset_row)
    db.commit()

    reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
    try:
        notifier.notify_password_reset(user.email, reset_url, settings.password_reset_expire_minutes)
    except Exception:
        pass  # don't leak send failures to the client -- same generic response either way

    return generic_response


@router.post("/reset-password")
@limiter.limit("10/hour")
def reset_password(request: Request, payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = _hash_token(payload.token)
    reset_row = db.query(models.PasswordResetToken).filter_by(token_hash=token_hash).first()

    invalid_error = HTTPException(
        status_code=400,
        detail="This reset link is invalid or has expired. Request a new one.",
    )

    if not reset_row:
        raise invalid_error
    if reset_row.used_at is not None:
        raise invalid_error
    if reset_row.expires_at < datetime.utcnow():
        raise invalid_error

    user = db.query(models.User).filter_by(id=reset_row.user_id).first()
    if not user:
        raise invalid_error

    user.hashed_password = security.hash_password(payload.new_password)
    user.token_version += 1  # invalidates every previously issued JWT for this user
    reset_row.used_at = datetime.utcnow()
    db.commit()

    return {"message": "Password updated. You've been logged out everywhere else for safety."}
