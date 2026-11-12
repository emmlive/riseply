"""Autopilot: applies by itself to strong matches, and only where it can do it safely.

Rules that never bend:
- Off until the person turns it on and confirms (autopilot_consent_at), and
  behind the server-wide auto-submit switch.
- Only matches at or above the person's own score (never below MIN_SCORE_FLOOR),
  at most their daily cap, a few per run.
- Only on the supported application systems (submitter.is_supported_ats). LinkedIn
  and Indeed are blocked outright.
- Only with a tailored resume that has readable contact details, and only for a
  posting that is still open.
- Never twice to the same company within DUPLICATE_DAYS, and each application is
  tried once. Anything the form needs a person for (an unanswered required
  question, a CAPTCHA, a resume that did not attach, a submit the site never
  confirmed) goes back to the person's review list with a note saying why.
- "Applied" is recorded only when the site confirms it. Every one is emailed.
"""
import threading
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app import models
from app.services import notifier, rise_index, submitter

MIN_SCORE_FLOOR = 75
PER_RUN_MAX = 6          # applications attempted in one run, across everyone
PER_USER_RUN_MAX = 3
DUPLICATE_DAYS = 30
BROWSER_DOWN = "Couldn't start the browser"

_lock = threading.Lock()


def _day_count(db: Session, user_id: int, now: datetime) -> int:
    return db.query(models.Application).filter(
        models.Application.user_id == user_id,
        models.Application.auto_applied_at.isnot(None),
        models.Application.auto_applied_at > now - timedelta(hours=24),
    ).count()


def _resume_readable(app_row: models.Application) -> bool:
    if not app_row.tailored_resume_data:
        return False
    try:
        from app.services import resume_customizer
        report = resume_customizer.ats_checks(resume_customizer.docx_to_blocks(app_row.tailored_resume_data))
        contact = next((c for c in report["checks"] if c["label"] == "Contact details"), None)
        return bool(contact and contact["ok"])
    except Exception:
        return False


def _applied_to_company_recently(db: Session, user_id: int, company: str, exclude_id: int, now: datetime) -> bool:
    if not (company or "").strip():
        return False
    rows = db.query(models.Application, models.Job).join(models.Job, models.Application.job_id == models.Job.id).filter(
        models.Application.user_id == user_id, models.Application.id != exclude_id,
        models.Application.status.in_(("approved", "submitted", "interviewing", "accepted")),
        models.Application.status_updated_at > now - timedelta(days=DUPLICATE_DAYS),
    ).all()
    return any((j.company or "").strip().lower() == company.strip().lower() for _, j in rows)


def eligible(db: Session, app_row: models.Application, job: models.Job, user: models.User, now: datetime) -> tuple[bool, str]:
    """(ok, why not). Everything here is a reason to leave the match for the person."""
    if not settings.auto_submit_enabled:
        return False, "The server's auto-submit switch is off."
    if not user.autopilot_enabled or not user.autopilot_consent_at:
        return False, "Autopilot is off for this person."
    if job.is_active is False:
        return False, "The posting is closed."
    if app_row.status != "pending_approval" or app_row.autopilot_tried_at is not None:
        return False, "Already handled."
    if (app_row.match_score or 0) < max(user.autopilot_min_score or 85, MIN_SCORE_FLOOR):
        return False, "Below the person's Autopilot score."
    ok, why = submitter.is_supported_ats(job.url or "")
    if not ok:
        return False, why
    if not _resume_readable(app_row):
        return False, "No tailored resume with readable contact details."
    if _applied_to_company_recently(db, user.id, job.company, app_row.id, now):
        return False, "Already applied to this company recently."
    return True, "ok"


def _give_back(db: Session, app_row: models.Application, now: datetime, detail: str) -> None:
    app_row.status = "pending_approval"
    app_row.status_updated_at = now
    app_row.notes = f"Autopilot didn't send this one: {detail} It is ready for you to review."
    db.commit()


def _attempt(db: Session, app_row, job, user, now, runner) -> dict:
    app_row.autopilot_tried_at = now
    app_row.status = "approved"
    app_row.status_updated_at = now
    db.commit()
    try:
        result = runner(app_row, job, user, actually_submit=True)
    except Exception as e:  # noqa: BLE001 - unattended: never let one failure stop the run
        result = {"status": "failed", "detail": f"Automation error: {e}"}
    if result.get("status") == "submitted":
        app_row.status = "submitted"
        app_row.submitted_at = app_row.auto_applied_at = now
        app_row.status_updated_at = now
        app_row.notes = "Applied by Autopilot."
        db.commit()
        try:
            rise_index.award_points(db, user, "mark_submitted", "Submitted an application (Autopilot)")
        except Exception as e:  # noqa: BLE001
            print(f"[autopilot] points failed for application {app_row.id}: {e}")
        try:
            notifier.send_email(
                user.notify_email or user.email,
                f"Riseply applied for you: {job.title} @ {job.company}",
                f"Autopilot just applied to {job.company} for {job.title} (a {app_row.match_score}% match) "
                f"with your tailored resume.\n{job.url}\n\nYou can see it in Applications. "
                "To change or stop Autopilot, open Profile.",
                kind="autopilot",
            )
        except Exception as e:  # noqa: BLE001
            print(f"[autopilot] email failed for application {app_row.id}: {e}")
        return result
    _give_back(db, app_row, now, result.get("detail") or "It needs you.")
    return result


def run(db: Session, now: datetime | None = None, runner=None) -> dict:
    """One pass: tries the best eligible matches for each Autopilot user."""
    now = now or datetime.utcnow()
    if runner is None:
        from app.routers.pipeline import _run_submitter, _ensure_posting_open  # lazy: the router imports services
    else:
        _ensure_posting_open = None
    out = {"applied": 0, "handed_back": 0, "stopped": ""}
    if not settings.auto_submit_enabled:
        out["stopped"] = "disabled"
        return out
    runner = runner or _run_submitter
    users = db.query(models.User).filter(models.User.autopilot_enabled.is_(True)).all()
    attempted = 0
    for user in users:
        remaining = (user.autopilot_daily_cap or 5) - _day_count(db, user.id, now)
        if remaining <= 0:
            continue
        rows = db.query(models.Application, models.Job).join(models.Job, models.Application.job_id == models.Job.id).filter(
            models.Application.user_id == user.id, models.Application.status == "pending_approval",
            models.Application.autopilot_tried_at.is_(None),
            models.Application.match_score >= max(user.autopilot_min_score or 85, MIN_SCORE_FLOOR),
        ).order_by(models.Application.match_score.desc(), models.Application.id.asc()).limit(25).all()
        tried_here = 0
        for app_row, job in rows:
            if remaining <= 0 or tried_here >= PER_USER_RUN_MAX or attempted >= PER_RUN_MAX:
                break
            ok, _why = eligible(db, app_row, job, user, now)
            if not ok:
                continue
            if _ensure_posting_open is not None:
                try:
                    _ensure_posting_open(db, app_row, job)   # closes it and raises when the posting is gone
                except Exception:
                    continue
            attempted += 1
            tried_here += 1
            result = _attempt(db, app_row, job, user, now, runner)
            if result.get("status") == "submitted":
                out["applied"] += 1
                remaining -= 1
            else:
                out["handed_back"] += 1
                if (result.get("detail") or "").startswith(BROWSER_DOWN):
                    out["stopped"] = "browser_unavailable"
                    return out
        if attempted >= PER_RUN_MAX:
            break
    return out


def run_background() -> None:
    """Entry point for the hourly trigger. One run at a time; an overlapping call does nothing."""
    from app.database import SessionLocal
    if not _lock.acquire(blocking=False):
        print("[autopilot] a run is already in progress; skipping")
        return
    db = SessionLocal()
    try:
        print(f"[autopilot] {run(db)}")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"[autopilot] run failed: {e}")
    finally:
        db.close()
        _lock.release()
