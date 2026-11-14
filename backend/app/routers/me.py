import secrets

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.config import settings
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
        alert_instant_min_score=user.alert_instant_min_score or 85,
        alert_digest_hour=8 if user.alert_digest_hour is None else user.alert_digest_hour,
        alert_timezone=user.alert_timezone or "",
        autopilot_enabled=bool(user.autopilot_enabled),
        autopilot_min_score=user.autopilot_min_score or 85,
        autopilot_daily_cap=user.autopilot_daily_cap or 5,
        autopilot_available=bool(settings.auto_submit_enabled),
        notification_channel=user.notification_channel or "email",
        sms_consent=bool(user.sms_consent),
        resume_text=user.resume_text or "",
        subscription_tier=user.subscription_tier or "free",
        subscription_status=user.subscription_status or "",
        is_admin=bool(user.is_admin),
        admin_role=user.admin_role or "",
        bookmarklet_token=(_ensure_bookmarklet_token(user, db) if db is not None else (user.bookmarklet_token or "")),
        used_welcome_search=bool(user.used_welcome_search),
        pro_until=user.pro_until,
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
    if "notification_preference" in updates and updates["notification_preference"] not in ("off", "every_match", "daily_digest", "smart"):
        raise HTTPException(status_code=400, detail="notification_preference must be off, every_match, daily_digest, or smart.")
    if updates.get("alert_timezone"):
        from app.services import job_alerts
        if not job_alerts.valid_timezone(updates["alert_timezone"]):
            raise HTTPException(status_code=400, detail="That time zone isn't recognized.")
    consent = updates.pop("autopilot_consent", None)
    if updates.get("autopilot_enabled"):
        if not (user.resume_text or "").strip():
            raise HTTPException(status_code=400, detail="Add your resume before turning on Autopilot.")
        phone = updates.get("phone", user.phone)
        location = updates.get("location", user.location)
        if not (phone or "").strip() or not (location or "").strip():
            raise HTTPException(status_code=400, detail="Add your phone number and location above first. Application forms ask for them.")
        if not user.autopilot_consent_at:
            if not consent:
                raise HTTPException(status_code=400, detail="Confirm that you want Riseply to submit applications on your behalf.")
            user.autopilot_consent_at = datetime.utcnow()
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


@router.get("/alerts/status")
def alert_status(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Why alerts are or are not arriving: setup, delivery and the daily search, each checked."""
    from app.services import alert_status as svc
    return svc.build(db, user)


@router.post("/alerts/preview")
def preview_alert(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sends the person a sample of the email smart alerts produce, built from
    their own latest matches (or two made-up ones if they have none yet), so
    they can see what they are choosing before they choose it."""
    from app.services import job_alerts, notifier
    now = datetime.utcnow()
    rows = db.query(models.Application, models.Job).join(models.Job, models.Application.job_id == models.Job.id).filter(
        models.Application.user_id == user.id).order_by(models.Application.created_at.desc()).limit(5).all()
    matches = [{"title": j.title, "company": j.company, "location": j.location, "match_score": a.match_score,
                "match_reason": a.match_reason, "url": j.url, "posted_at": j.posted_at, "salary_min": j.salary_min,
                "salary_max": j.salary_max, "salary_currency": j.salary_currency, "salary_is_predicted": j.salary_is_predicted}
               for a, j in rows]
    sample = not matches
    if sample:
        matches = [
            {"title": "Senior IT Auditor", "company": "Example Corp", "location": "Chicago, IL", "match_score": 91,
             "match_reason": "Your SOX and ITGC experience lines up with their top requirements.", "url": "", "posted_at": now},
            {"title": "GRC Analyst", "company": "Sample Bank", "location": "Remote", "match_score": 72,
             "match_reason": "Strong control testing background; they also want a CISA, which you hold.", "url": "", "posted_at": now - timedelta(days=2)},
        ]
    chosen = job_alerts.choose(matches, user.alert_instant_min_score or 85)
    subject = "Preview: " + job_alerts.subject_for(chosen)
    text = ("This is a preview of your Riseply alerts" + (" (sample jobs, since you have no matches yet)" if sample else " using your latest matches") + ".\n\n"
            + job_alerts.digest_text(chosen, now))
    notifier.send_alert_digest(user.notify_email or user.email, subject, text, job_alerts.digest_html(chosen, now), kind="test")
    return {"sent_to": user.notify_email or user.email, "sample": sample, "discord": _preview_discord(db, user, matches)}


def _preview_discord(db: Session, user: models.User, matches: list[dict]) -> str:
    """Sends the same sample to Discord and says what happened:
    sent | not_connected | alerts_off | failed."""
    from app.services import discord_notify
    conn = db.query(models.DiscordConnection).filter_by(user_id=user.id).first()
    if not conn or not conn.enabled:
        return "not_connected"
    if not conn.matches_enabled:
        return "alerts_off"
    before = conn.last_success_at
    try:
        discord_notify.notify_digest(db, user, matches)
    except Exception as e:
        print(f"[alerts] preview Discord failed for user {user.id}: {e}")
        return "failed"
    db.refresh(conn)
    return "sent" if conn.last_success_at and conn.last_success_at != before else "failed"
