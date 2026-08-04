from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.config import settings

LIMITS = {
    "match": settings.free_tier_max_matches_per_month,
    "tailor_resume": settings.free_tier_max_tailored_resumes_per_month,
}


def _current_period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def get_usage(db: Session, user_id: int, action: str) -> int:
    period = _current_period()
    row = db.query(models.UsageLog).filter_by(
        user_id=user_id, period=period, action=action
    ).first()
    return row.count if row else 0


def check_and_increment(db: Session, user_id: int, action: str, amount: int = 1):
    """Raises HTTP 429 if this action would exceed the user's monthly limit.
    Otherwise increments the counter and returns the new count.

    Call this BEFORE making the Claude API call it's metering, so a user
    who's hit their cap never triggers the paid call in the first place.
    """
    limit = LIMITS.get(action)
    if limit is None:
        return  # unmetered action

    period = _current_period()
    row = db.query(models.UsageLog).filter_by(
        user_id=user_id, period=period, action=action
    ).first()

    current = row.count if row else 0
    if current + amount > limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly limit reached for '{action}' ({limit}/month on the free tier). "
                f"This resets next month, or consider leaving a tip to support higher limits."
            ),
        )

    if row:
        row.count += amount
    else:
        row = models.UsageLog(user_id=user_id, period=period, action=action, count=amount)
        db.add(row)
    db.commit()
    return current + amount
