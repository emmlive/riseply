"""When an application moves to "interviewing": get the person ready without
them having to ask.

Runs in the background so marking the interview never waits on an AI call.
It (1) writes the interview prep brief if there isn't one and the person has
quota left, counted against their normal monthly allowance and refunded on
failure, and (2) emails them what to do next: the prep, a mock interview and
salary-negotiation practice. Every step is best-effort: a failure here is
logged and never affects the status change.
"""
from urllib.parse import urlencode

from fastapi import HTTPException

from app import models
from app.config import settings
from app.services import interview_prep as interview_prep_service
from app.services import notifier, usage


def _practice_url(role: str, kind: str) -> str:
    q = urlencode({"role": role[:120], "type": kind})
    return f"{settings.frontend_url.rstrip('/')}/dashboard/career-coach?{q}"


def email_body(job_title: str, company: str, prep_ready: bool) -> str:
    base = settings.frontend_url.rstrip("/")
    prep_line = (
        "Your interview prep for this role is ready on your Applications page."
        if prep_ready else
        "Open your Applications page and click Interview prep to get your brief for this role."
    )
    return (
        f"Congratulations on the interview for {job_title} at {company}.\n\n"
        f"{prep_line}\n{base}/dashboard/applications\n\n"
        "Next steps that help most:\n"
        f"- Run a mock interview for this role (voice mode available): {_practice_url(job_title, 'interview')}\n"
        f"- If an offer comes, practice the negotiation first: {_practice_url(job_title, 'negotiation')}\n"
        f"- Read your company brief and write your thank-you note from the same page.\n\n"
        "Good luck. Come back and tell us how it went."
    )


def prepare(application_id: int) -> None:
    """Entry point for the background task. Opens its own session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        app_row = db.get(models.Application, application_id)
        if not app_row or app_row.status != "interviewing":
            return
        user = db.get(models.User, app_row.user_id)
        job = db.get(models.Job, app_row.job_id)
        if not user or not job:
            return

        prep = db.query(models.InterviewPrep).filter_by(application_id=application_id).first()
        if not prep and (user.resume_text or "").strip():
            try:
                usage.check_and_increment(db, user, "interview_prep", 1)
            except HTTPException:
                pass  # out of allowance: the email tells them how to get it later
            else:
                try:
                    brief = interview_prep_service.generate_prep_brief(
                        user.resume_text,
                        {"title": job.title, "company": job.company, "description": job.description},
                    )
                    prep = models.InterviewPrep(application_id=application_id, user_id=user.id, brief=brief)
                    db.add(prep)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    usage.decrement(db, user.id, "interview_prep", 1)
                    print(f"[interview_auto] prep failed for application {application_id}: {e}")

        if (user.notification_preference or "every_match") != "off" and (user.notification_channel or "email") in ("email", "both"):
            try:
                notifier.send_email(
                    user.notify_email or user.email,
                    f"Interview coming up: {job.title} @ {job.company}",
                    email_body(job.title, job.company, prep_ready=bool(prep)),
                    kind="interview_ready",
                )
            except Exception as e:
                print(f"[interview_auto] email failed for application {application_id}: {e}")
    except Exception as e:
        print(f"[interview_auto] unexpected failure for application {application_id}: {e}")
    finally:
        db.close()
