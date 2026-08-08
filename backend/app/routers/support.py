from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.config import settings
from app.database import get_db
from app.security import get_current_user
from app.services import notifier
from app import models, schemas

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/contact")
def contact_support(
    payload: schemas.SupportContactRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Always persist the message first -- this is now the source of truth
    # (visible to admins in-app), so a message is never lost even if
    # SMTP isn't configured or a send fails.
    msg = models.SupportMessage(
        user_id=user.id, subject=payload.subject, message=payload.message,
    )
    db.add(msg)
    db.commit()

    support_inbox = settings.support_email or settings.smtp_user
    if support_inbox:
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
        except Exception as e:
            print(f"[support] Failed to email support inbox for message {msg.id}: {e}")

    return {"sent": True}
