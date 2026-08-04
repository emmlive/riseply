from datetime import date, datetime, timedelta
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app import models

# Points are awarded ONLY for effort — actions the user actually took.
# Never for outcomes (landing an interview, getting an offer) — those
# are partly out of the user's control, and turning them into a score
# would quietly punish people for rejections that aren't their fault.
POINT_VALUES = {
    "run_search": 2,
    "review_match": 3,       # approve or reject — reviewing is the effort
    "approve_match": 3,
    "mark_submitted": 15,    # the real milestone: actually applying
    "generate_interview_prep": 10,
    "generate_onboarding_plan": 10,
    "job_buddy_message": 2,
}

# Minimum number of applications before a company's stats are shown
# publicly. Below this, individual users could be re-identified from an
# aggregate ("the only applicant" isn't really anonymous) — so we hide
# the stat entirely rather than show a misleading tiny sample.
MIN_SAMPLE_SIZE = 5


def record_activity(db: Session, user: models.User):
    """Updates the user's daily streak. Call this on any meaningful
    check-in, whether or not it also awards points."""
    today = date.today()
    if user.last_active_date == today:
        pass  # already counted today
    elif user.last_active_date == today - timedelta(days=1):
        user.current_streak += 1
        user.longest_streak = max(user.longest_streak, user.current_streak)
        user.last_active_date = today
    else:
        user.current_streak = 1
        user.longest_streak = max(user.longest_streak, 1)
        user.last_active_date = today
    db.commit()


def award_points(db: Session, user: models.User, action: str, reason: str):
    amount = POINT_VALUES.get(action, 0)
    if amount <= 0:
        record_activity(db, user)
        return

    user.rise_points += amount
    db.add(models.PointsEvent(user_id=user.id, amount=amount, reason=reason))
    db.commit()
    record_activity(db, user)


def company_stats(db: Session, company: str) -> dict | None:
    """Aggregate, anonymized response stats for one company, across ALL
    users. Returns None if the sample is too small to show safely."""
    applied = db.query(models.Application).join(models.Job).filter(
        models.Job.company == company,
        models.Application.submitted_at.isnot(None),
    )
    applied_count = applied.count()
    if applied_count < MIN_SAMPLE_SIZE:
        return None

    heard_back_count = applied.filter(
        models.Application.status.in_(["interviewing", "accepted"])
    ).count()

    # Average days to hear back, for the ones who did
    avg_days_row = db.query(
        func.avg(
            func.julianday(models.Application.status_updated_at)
            - func.julianday(models.Application.submitted_at)
        )
    ).join(models.Job).filter(
        models.Job.company == company,
        models.Application.submitted_at.isnot(None),
        models.Application.status.in_(["interviewing", "accepted"]),
    ).scalar()

    return {
        "company": company,
        "applied_count": applied_count,
        "response_rate": round(100 * heard_back_count / applied_count),
        "avg_days_to_respond": round(avg_days_row) if avg_days_row else None,
    }


def trending_companies(db: Session, days: int = 14, limit: int = 20) -> list[dict]:
    """Companies with the most application activity in the last N days,
    among those with enough volume to report on safely."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.query(
        models.Job.company,
        func.count(models.Application.id).label("recent_applications"),
    ).join(models.Application, models.Application.job_id == models.Job.id).filter(
        models.Application.submitted_at.isnot(None),
        models.Application.submitted_at >= since,
    ).group_by(models.Job.company).order_by(
        func.count(models.Application.id).desc()
    ).limit(limit * 2).all()  # over-fetch since some will fail the min-sample check below

    results = []
    for company, recent_count in rows:
        stats = company_stats(db, company)
        if stats:
            stats["recent_applications"] = recent_count
            results.append(stats)
        if len(results) >= limit:
            break

    return results
