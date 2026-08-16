import secrets

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import resume_parser

router = APIRouter(prefix="/me", tags=["me"])

MAX_RESUME_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB -- generous for a resume, guards against abuse


def _ensure_bookmarklet_token(user: models.User, db: Session) -> str:
    """Lazily generates and persists a bookmarklet_token on first
    access, rather than at signup -- most users will never use the
    bookmarklet feature, so there's no reason to write a token for
    every account up front. Same secrets.token_urlsafe(32) pattern
    already used for password-reset tokens elsewhere in this codebase.
    """
    if not user.bookmarklet_token:
        user.bookmarklet_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(user)
    return user.bookmarklet_token


def _to_out(user: models.User, db: Session | None = None) -> schemas.UserOut:
    """Coalesces any unexpected NULLs to sensible defaults before
    serialization. Every real signup goes through the ORM, which applies
    each column's default -- so this shouldn't fire in practice -- but
    it's cheap insurance against a response crash if a row was ever
    touched outside the normal app flow (a manual DB fix, a future
    migration, etc.).

    db is optional (None only for callers that don't need
    bookmarklet_token populated, e.g. contexts with no session handy) --
    passing it enables the lazy-generation path in
    _ensure_bookmarklet_token above.
    """
    return schemas.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name or "",
        phone=user.phone or "",
        location=user.location or "",
        linkedin_url=user.linkedin_url or "",
        portfolio_url=user.portfolio_url or "",
        notify_email=user.notify_email or user.email,
        auto_submit=bool(user.auto_submit),
        notification_preference=user.notification_preference or "every_match",
        notification_min_score=user.notification_min_score or 0,
        notification_channel=user.notification_channel or "email",
        sms_consent=bool(user.sms_consent),
        resume_text=user.resume_text or "",
        subscription_tier=user.subscription_tier or "free",
        subscription_status=user.subscription_status or "",
        is_admin=bool(user.is_admin),
        admin_role=user.admin_role or "",
        bookmarklet_token=(_ensure_bookmarklet_token(user, db) if db is not None else (user.bookmarklet_token or "")),
        used_welcome_search=bool(user.used_welcome_search),
    )


@router.get("", response_model=schemas.UserOut)
def get_me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_out(user, db)


@router.patch("", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updates = payload.model_dump(exclude_unset=True)
    if "notification_preference" in updates and updates["notification_preference"] not in ("off", "every_match", "daily_digest"):
        raise HTTPException(status_code=400, detail="notification_preference must be off, every_match, or daily_digest.")
    if "notification_channel" in updates and updates["notification_channel"] not in ("email", "sms", "both"):
        raise HTTPException(status_code=400, detail="notification_channel must be email, sms, or both.")

    # Resolve what the channel and consent WILL be after this update,
    # not just what's in this specific payload -- e.g. someone already
    # has sms_consent=True from before and is only changing the channel
    # now, or vice versa.
    resulting_channel = updates.get("notification_channel", user.notification_channel or "email")
    resulting_consent = updates.get("sms_consent", user.sms_consent)
    resulting_phone = updates.get("phone", user.phone)
    if resulting_channel in ("sms", "both"):
        if not resulting_consent:
            raise HTTPException(status_code=400, detail="SMS notifications require checking the SMS consent box first.")
        if not (resulting_phone or "").strip():
            raise HTTPException(status_code=400, detail="Add a phone number before enabling SMS notifications.")

    # Record WHEN consent was actually given -- true compliance value,
    # not just a boolean with no paper trail. Only stamps it on the
    # transition to true, never overwrites an existing consent record
    # just because some other field changed in the same request.
    if updates.get("sms_consent") is True and not user.sms_consent:
        user.sms_consent_at = datetime.utcnow()
    if updates.get("sms_consent") is False:
        user.sms_consent_at = None

    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _to_out(user, db)


@router.put("/resume", response_model=schemas.UserOut)
def update_resume(
    payload: schemas.ResumeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.resume_text = payload.resume_text
    db.commit()
    db.refresh(user)
    return _to_out(user, db)


@router.post("/resume/parse", response_model=schemas.ResumeParseOut)
async def parse_resume_file(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
):
    """Extracts text from an uploaded PDF/DOCX -- does NOT save it. The
    frontend shows the extracted text for review/editing, and the user
    explicitly saves it via PUT /me/resume, same as pasting text by hand.
    This avoids silently overwriting an existing resume with a bad
    extraction (e.g. a scanned PDF that yields garbage or empty text)."""
    contents = await file.read()
    if len(contents) > MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large — please keep it under 10MB.")

    text = resume_parser.extract_resume_text(file.filename or "", contents)
    return schemas.ResumeParseOut(resume_text=text)


@router.post("/regenerate-bookmarklet-token", response_model=schemas.UserOut)
def regenerate_bookmarklet_token(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invalidates any previously-issued bookmarklet link -- the old
    token stops resolving to anything (see GET /bookmarklet.js), so a
    link that's been exposed somewhere it shouldn't (shared by
    accident, saved on a public machine, etc) can be cut off without
    needing to change a password or any other credential.
    """
    user.bookmarklet_token = secrets.token_urlsafe(32)
    db.commit()
    db.refresh(user)
    return _to_out(user, db)
