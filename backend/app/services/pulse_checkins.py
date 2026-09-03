"""Creates new pulse check-ins on a recurring cadence -- same
"coarse but honest" spirit as mentor_reminders.py and
certification_reminders.py: a simple interval guard, no smart
scheduling. Meant to be triggered daily by the same external
scheduler that already calls culture-bot-run and the other reminder
jobs.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.services import notifier

CHECKIN_INTERVAL_DAYS = 30


def run_pulse_checkin_creation(db: Session) -> dict:
    """One check-in per active, org-affiliated employee roughly every
    CHECKIN_INTERVAL_DAYS -- an employee is due for a new one if
    they've never had one, or their most recent one was sent at least
    that long ago (regardless of whether they answered it -- an
    unanswered prompt isn't grounds to withhold the next one
    indefinitely; life moves on and the temperature check should keep
    happening on schedule)."""
    created = 0

    active_apps = db.query(models.Application).filter(
        models.Application.organization_id.isnot(None),
        models.Application.is_archived == False,  # noqa: E712
    ).all()

    for app_row in active_apps:
        latest = (
            db.query(models.PulseCheckIn)
            .filter_by(application_id=app_row.id)
            .order_by(models.PulseCheckIn.sent_at.desc())
            .first()
        )
        if latest and latest.sent_at > datetime.utcnow() - timedelta(days=CHECKIN_INTERVAL_DAYS):
            continue  # not due yet

        checkin = models.PulseCheckIn(application_id=app_row.id)
        db.add(checkin)
        db.commit()
        created += 1

        user = db.query(models.User).filter_by(id=app_row.user_id).first()
        if user:
            try:
                notifier.send_email(
                    user.notify_email or user.email,
                    "Quick check-in — how's it going?",
                    "A 10-second pulse check is waiting for you in Job Buddy. Your answer stays private.",
                )
            except Exception:
                pass  # best-effort -- the check-in itself is already created either way

    return {"pulse_checkins_created": created}
