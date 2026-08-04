from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.security import get_current_user
from app.services import notifier
from app import models, schemas

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/contact")
def contact_support(
    payload: schemas.SupportContactRequest,
    user: models.User = Depends(get_current_user),
):
    support_inbox = settings.support_email or settings.smtp_user
    if not support_inbox:
        raise HTTPException(
            status_code=503,
            detail="Support isn't configured yet — email us directly in the meantime.",
        )

    try:
        notifier.send_email(
            support_inbox,
            f"[Riseply Support] {payload.subject}",
            (
                f"From: {user.full_name or '(no name)'} <{user.email}>\n"
                f"User ID: {user.id}\n\n"
                f"{payload.message}"
            ),
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Couldn't send your message right now — try again shortly, or email us directly.",
        )
    return {"sent": True}
