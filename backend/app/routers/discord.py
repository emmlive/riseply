from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.rate_limit import limiter
from app.security import get_current_user
from app.services import calendar_encryption
from app.services import discord_notify as dn
from app import models, schemas

# Per-user Discord connection for momentum notifications. The webhook URL
# is write-only: it's accepted on connect, stored encrypted, and never
# returned -- GET shows only a masked hint.
router = APIRouter(prefix="/discord", tags=["discord"])


def _status(conn: models.DiscordConnection | None) -> schemas.DiscordStatusOut:
    if not conn:
        return schemas.DiscordStatusOut()
    return schemas.DiscordStatusOut(
        connected=True, webhook_hint=conn.webhook_hint or "", enabled=bool(conn.enabled),
        nudge_enabled=bool(conn.nudge_enabled), progress_enabled=bool(conn.progress_enabled),
        followup_enabled=bool(conn.followup_enabled), matches_enabled=bool(conn.matches_enabled),
        nudge_hour=conn.nudge_hour if conn.nudge_hour is not None else 18,
        timezone=conn.timezone or "UTC", last_error=conn.last_error or "",
        last_success_at=conn.last_success_at,
    )


def _get(db: Session, user: models.User) -> models.DiscordConnection | None:
    return db.query(models.DiscordConnection).filter_by(user_id=user.id).first()


def _require(db: Session, user: models.User) -> models.DiscordConnection:
    conn = _get(db, user)
    if not conn:
        raise HTTPException(status_code=404, detail="Discord isn't connected.")
    return conn


@router.get("", response_model=schemas.DiscordStatusOut)
def get_status(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _status(_get(db, user))


@router.put("/connect", response_model=schemas.DiscordStatusOut)
@limiter.limit("10/hour")
def connect(
    request: Request,
    payload: schemas.DiscordConnectRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    url = payload.webhook_url.strip()
    if not dn.parse_webhook(url):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a Discord webhook URL. It should start with https://discord.com/api/webhooks/",
        )
    if not dn.valid_timezone(payload.timezone):
        raise HTTPException(status_code=400, detail="Unknown timezone.")

    # Fails with a clear message if the server has no encryption key,
    # rather than ever storing the URL in plaintext.
    try:
        encrypted = calendar_encryption.encrypt_token(url)
    except HTTPException:
        raise HTTPException(
            status_code=503,
            detail="Discord notifications aren't configured on the server yet (CALENDAR_TOKEN_ENCRYPTION_KEY is unset).",
        )

    # Prove the webhook works (and that the person can see the channel)
    # by posting a real message before saving anything.
    ok, status, _err = dn._post(url, dn.build_payload(
        "Riseply is connected ✅",
        "You'll get practice nudges, streak reminders and progress recaps here. Change what you receive any time in your Riseply profile.",
        url=dn._coach_link(),
    ))
    if not ok:
        detail = ("Discord says that webhook doesn't exist. Check you copied the whole URL."
                  if status in (401, 403, 404) else "Couldn't send a test message to that webhook. Try again in a moment.")
        raise HTTPException(status_code=400, detail=detail)

    conn = _get(db, user)
    if not conn:
        conn = models.DiscordConnection(user_id=user.id)
        db.add(conn)
    conn.webhook_url_enc = encrypted
    conn.webhook_hint = dn.hint_for(url)
    conn.timezone = payload.timezone
    conn.enabled = True
    conn.consecutive_failures = 0
    conn.last_error = ""
    conn.last_success_at = dn.datetime.utcnow()
    db.commit()
    db.refresh(conn)
    return _status(conn)


@router.patch("/settings", response_model=schemas.DiscordStatusOut)
def update_settings(
    payload: schemas.DiscordSettingsUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    conn = _require(db, user)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("timezone") is not None and not dn.valid_timezone(updates["timezone"]):
        raise HTTPException(status_code=400, detail="Unknown timezone.")
    if updates.get("enabled") is True:
        # Turning it back on clears the old failure state.
        conn.consecutive_failures = 0
        conn.last_error = ""
    for k, v in updates.items():
        if v is not None:
            setattr(conn, k, v)
    db.commit()
    db.refresh(conn)
    return _status(conn)


@router.post("/test")
@limiter.limit("10/hour")
def send_test(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    conn = _require(db, user)
    ok = dn.send(db, conn, dn.build_payload(
        "Test message from Riseply", "If you can read this, your Discord connection is working. 🎉", url=dn._coach_link(),
    ))
    if not ok:
        db.refresh(conn)
        raise HTTPException(status_code=502, detail=conn.last_error or "Couldn't deliver the test message.")
    return {"sent": True}


@router.delete("")
def disconnect(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    conn = _get(db, user)
    if conn:
        db.delete(conn)
        db.commit()
    return {"disconnected": True}
