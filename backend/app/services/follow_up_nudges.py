"""Gentle nudge for applications that have gone quiet.

A week or more after an application was submitted with no change in status,
one email per person lists up to five of them and points to the Applications
page, where the follow-up draft and networking messages are one click away.
Each application is nudged once. No AI call, so no cost. Meant to run daily
from the same scheduler that calls culture-bot-run.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import notifier

QUIET_AFTER_DAYS = 7
GIVE_UP_AFTER_DAYS = 30   # past this, a nudge is noise
MAX_PER_EMAIL = 5


def email_body(rows: list[tuple[str, str, int]]) -> str:
    base = settings.frontend_url.rstrip("/")
    lines = [f"- {title} at {company}: submitted {days} days ago" for title, company, days in rows]
    return (
        "These applications haven't had a reply yet:\n\n" + "\n".join(lines) + "\n\n"
        "A short, polite follow-up a week or two after applying often gets a response. "
        "Open an application and click Draft follow-up, or Write networking messages to reach someone at the company:\n"
        f"{base}/dashboard/applications\n\n"
        "We only remind you once per application."
    )


def run_follow_up_nudges(db: Session) -> dict:
    now = datetime.utcnow()
    due = (
        db.query(models.Application, models.Job)
        .join(models.Job, models.Job.id == models.Application.job_id)
        .filter(
            models.Application.status == "submitted",
            models.Application.submitted_at.isnot(None),
            models.Application.submitted_at <= now - timedelta(days=QUIET_AFTER_DAYS),
            models.Application.submitted_at >= now - timedelta(days=GIVE_UP_AFTER_DAYS),
            models.Application.follow_up_nudged_at.is_(None),
            models.Application.is_archived.is_(False),
            models.Application.deleted_at.is_(None),
            models.Application.organization_id.is_(None),
        )
        .order_by(models.Application.submitted_at.asc())
        .all()
    )
    by_user: dict[int, list[tuple[models.Application, models.Job]]] = {}
    for a, j in due:
        by_user.setdefault(a.user_id, []).append((a, j))

    emails = 0
    for user_id, items in by_user.items():
        user = db.get(models.User, user_id)
        if not user or user.is_suspended:
            continue
        if (user.notification_preference or "every_match") == "off" or (user.notification_channel or "email") not in ("email", "both"):
            for a, _ in items:  # not nudging this person: don't pile them up for later
                a.follow_up_nudged_at = now
            db.commit()
            continue
        batch = items[:MAX_PER_EMAIL]
        rows = [(j.title, j.company, (now - a.submitted_at).days) for a, j in batch]
        try:
            notifier.send_email(
                user.notify_email or user.email,
                f"{len(batch)} application{'s' if len(batch) != 1 else ''} waiting on a reply",
                email_body(rows), kind="follow_up_nudge",
            )
        except Exception as e:
            print(f"[follow_up_nudges] email failed for user {user_id}: {e}")
            continue  # leave them unmarked: try again tomorrow
        for a, _ in batch:
            a.follow_up_nudged_at = now
        db.commit()
        emails += 1
    return {"follow_up_nudge_emails": emails}
