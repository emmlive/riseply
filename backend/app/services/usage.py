from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.config import settings

FREE_LIMITS = {
    "match": settings.free_tier_max_matches_per_month,
    "tailor_resume": settings.free_tier_max_tailored_resumes_per_month,
    "interview_prep": settings.free_tier_max_interview_preps_per_month,
    "onboarding_plan": settings.free_tier_max_onboarding_plans_per_month,
    "job_buddy_message": settings.free_tier_max_job_buddy_messages_per_month,
    "org_ask": settings.free_tier_max_org_ask_per_month,
}

PRO_LIMITS = {
    "match": settings.pro_tier_max_matches_per_month,
    "tailor_resume": settings.pro_tier_max_tailored_resumes_per_month,
    "interview_prep": settings.pro_tier_max_interview_preps_per_month,
    "onboarding_plan": settings.pro_tier_max_onboarding_plans_per_month,
    "job_buddy_message": settings.pro_tier_max_job_buddy_messages_per_month,
    "org_ask": settings.pro_tier_max_org_ask_per_month,
}


def is_pro(user: models.User) -> bool:
    """A user is on Pro only while Stripe confirms an active subscription --
    never just because the tier column says so, since that column can lag
    a cancellation until the next webhook fires.

    Admin accounts are always treated as Pro, regardless of billing state.
    This is deliberate: admins need to exercise every Pro-gated feature
    (higher limits, more search profiles, Org Buddy testing) without an
    actual Stripe subscription, since these accounts exist for internal
    testing, not paying customers."""
    if user.is_admin:
        return True
    return user.subscription_tier == "pro" and user.subscription_status == "active"


def limits_for(user: models.User) -> dict:
    return PRO_LIMITS if is_pro(user) else FREE_LIMITS


def max_search_profiles(user: models.User) -> int:
    return settings.pro_tier_max_search_profiles if is_pro(user) else settings.free_tier_max_search_profiles


def _current_period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def get_usage(db: Session, user_id: int, action: str) -> int:
    period = _current_period()
    row = db.query(models.UsageLog).filter_by(
        user_id=user_id, period=period, action=action
    ).first()
    return row.count if row else 0


def check_and_increment(db: Session, user: models.User, action: str, amount: int = 1):
    """Raises HTTP 429 if this action would exceed the user's monthly limit
    for their current tier. Otherwise increments the counter and returns
    the new count.

    Call this BEFORE making the Claude API call it's metering. If the call
    you're metering can fail, pair this with decrement() in a try/except
    so a failed generation doesn't cost the user part of their monthly
    allowance for nothing.
    """
    limit = limits_for(user).get(action)
    if limit is None:
        return  # unmetered action

    period = _current_period()
    row = db.query(models.UsageLog).filter_by(
        user_id=user.id, period=period, action=action
    ).first()

    current = row.count if row else 0
    if current + amount > limit:
        upgrade_hint = "" if is_pro(user) else " Upgrade to Pro for higher limits."
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly limit reached for '{action}' ({limit}/month on your current plan). "
                f"This resets next month.{upgrade_hint}"
            ),
        )

    if row:
        row.count += amount
    else:
        row = models.UsageLog(user_id=user.id, period=period, action=action, count=amount)
        db.add(row)
    db.commit()
    return current + amount


def decrement(db: Session, user_id: int, action: str, amount: int = 1):
    """Compensating decrement for when a metered call was counted but then
    failed -- e.g. the Claude API call itself errored after the usage
    check passed. Never goes below zero.

    Also logs a FailureLog row -- this function is only ever called from
    the exact points where a paid Claude call genuinely failed, which
    makes it a real error-rate signal rather than a synthetic one.
    """
    period = _current_period()
    row = db.query(models.UsageLog).filter_by(
        user_id=user_id, period=period, action=action
    ).first()
    if row and row.count > 0:
        row.count = max(0, row.count - amount)

    db.add(models.FailureLog(user_id=user_id, action=action))
    db.commit()
