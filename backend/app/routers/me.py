from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user

router = APIRouter(prefix="/me", tags=["me"])


def _to_out(user: models.User) -> schemas.UserOut:
    """Coalesces any unexpected NULLs to sensible defaults before
    serialization. Every real signup goes through the ORM, which applies
    each column's default -- so this shouldn't fire in practice -- but
    it's cheap insurance against a response crash if a row was ever
    touched outside the normal app flow (a manual DB fix, a future
    migration, etc.)."""
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
        resume_text=user.resume_text or "",
        subscription_tier=user.subscription_tier or "free",
        subscription_status=user.subscription_status or "",
        is_admin=bool(user.is_admin),
    )


@router.get("", response_model=schemas.UserOut)
def get_me(user: models.User = Depends(get_current_user)):
    return _to_out(user)


@router.patch("", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.put("/resume", response_model=schemas.UserOut)
def update_resume(
    payload: schemas.ResumeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.resume_text = payload.resume_text
    db.commit()
    db.refresh(user)
    return _to_out(user)
