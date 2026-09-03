"""Mentorship check-in reminders -- nudges a pairing that's gone quiet.

Same "coarse but honest" spirit as culture_bot.py: no smart scheduling,
no per-pair customization, just "has it been N days since the last
signal of activity on this pairing" checked against a simple
timestamp guard, the same reminder_sent_at pattern LessonDelivery
already uses. Meant to be triggered daily by the same external
scheduler that already calls culture-bot-run and scheduled-run.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.services import notifier

REMINDER_AFTER_DAYS = 21  # ~3 weeks with no logged meeting


def run_mentorship_reminders(db: Session) -> dict:
    """For every active mentor pairing, finds the most recent signal of
    activity -- either the latest logged meeting, or the assignment
    date itself if no meeting has ever been logged -- and sends a
    check-in nudge to both the employee and the mentor if that's more
    than REMINDER_AFTER_DAYS old and no reminder has gone out since.

    Logging a new meeting resets reminder_last_sent_at back to None
    (see log_mentor_meeting in org_buddy.py), so a pairing that's
    actually active never gets nagged -- this only fires for pairings
    that have genuinely gone quiet.

    Idempotent via the same guard-timestamp approach as everywhere else
    in this codebase: re-running this twice in a day doesn't double-
    send, since reminder_last_sent_at gets set right after the first
    successful send.
    """
    sent = 0

    assignments = db.query(models.MentorAssignment).all()
    for assignment in assignments:
        if assignment.reminder_last_sent_at is not None:
            continue  # already nudged since the last real activity

        latest_meeting = (
            db.query(models.MentorMeetingLog)
            .filter_by(mentor_assignment_id=assignment.id)
            .order_by(models.MentorMeetingLog.meeting_date.desc())
            .first()
        )
        last_activity = (
            datetime.combine(latest_meeting.meeting_date, datetime.min.time())
            if latest_meeting else assignment.assigned_at
        )
        if (datetime.utcnow() - last_activity).days < REMINDER_AFTER_DAYS:
            continue

        application = db.query(models.Application).filter_by(id=assignment.application_id).first()
        contact = db.query(models.OrgHumanContact).filter_by(id=assignment.contact_id).first()
        if not application or not contact:
            continue
        employee = db.query(models.User).filter_by(id=application.user_id).first()
        if not employee:
            continue

        body = (
            "It's been a few weeks since your last logged mentorship meeting -- "
            "might be a good time to check in with each other. You can log your "
            "next meeting from the mentorship section of the app."
        )
        try:
            notifier.send_email(employee.notify_email or employee.email, "Time to check in with your mentor?", body)
            notifier.send_email(contact.email, "Time to check in with your mentee?", body)
        except Exception:
            continue

        assignment.reminder_last_sent_at = datetime.utcnow()
        db.commit()
        sent += 1

    return {"mentorship_reminders_sent": sent}
