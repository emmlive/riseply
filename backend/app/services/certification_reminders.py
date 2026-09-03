"""Certification expiration reminders -- nudges an employee whose
certification is expiring soon or has already lapsed.

Same "coarse but honest" spirit as mentor_reminders.py and
culture_bot.py: a simple timestamp guard, no smart scheduling. Meant
to be triggered daily by the same external scheduler that already
calls culture-bot-run, scheduled-run, and the mentorship reminders.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.services import notifier

REMINDER_BEFORE_DAYS = 30  # start nudging a month before expiration


def run_certification_reminders(db: Session) -> dict:
    """Only considers each (application, requirement) pair's MOST
    RECENT completion -- a renewal creates a genuinely new
    EmployeeCertification row (see complete_requirement's own
    docstring), so an older, already-superseded record shouldn't
    trigger a reminder just because it happens to still exist in the
    history. Completing a fresh renewal naturally resets the guard,
    since the new row starts with reminder_last_sent_at=None.

    Fires once someone is within REMINDER_BEFORE_DAYS of expiring, and
    again is possible only after that specific completion record is
    superseded by a new one -- this deliberately does NOT re-remind
    daily once already nudged for a given completion, same guard
    pattern as mentorship reminders."""
    sent = 0

    candidates = (
        db.query(models.EmployeeCertification)
        .filter(models.EmployeeCertification.expires_at.isnot(None))
        .order_by(models.EmployeeCertification.completed_at.desc())
        .all()
    )
    latest_by_pair: dict[tuple[int, int], models.EmployeeCertification] = {}
    for cert in candidates:
        key = (cert.application_id, cert.requirement_id)
        if key not in latest_by_pair:  # first one seen per pair, thanks to the desc() order, is the latest
            latest_by_pair[key] = cert

    for cert in latest_by_pair.values():
        if cert.reminder_last_sent_at is not None:
            continue

        days_until_expiry = (cert.expires_at - datetime.utcnow()).days
        if days_until_expiry > REMINDER_BEFORE_DAYS:
            continue  # not due yet

        application = db.query(models.Application).filter_by(id=cert.application_id).first()
        requirement = db.query(models.CertificationRequirement).filter_by(id=cert.requirement_id).first()
        if not application or not requirement:
            continue
        employee = db.query(models.User).filter_by(id=application.user_id).first()
        if not employee:
            continue

        if cert.expires_at < datetime.utcnow():
            subject = f'Your "{requirement.name}" certification has expired'
            body = (
                f'Your "{requirement.name}" certification expired on '
                f"{cert.expires_at.date()}. Please renew it as soon as you can."
            )
        else:
            subject = f'Your "{requirement.name}" certification is expiring soon'
            body = (
                f'Your "{requirement.name}" certification expires on '
                f"{cert.expires_at.date()}. Please renew it before then."
            )

        try:
            notifier.send_email(employee.notify_email or employee.email, subject, body)
        except Exception:
            continue

        cert.reminder_last_sent_at = datetime.utcnow()
        db.commit()
        sent += 1

    return {"certification_reminders_sent": sent}
