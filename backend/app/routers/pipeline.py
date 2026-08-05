import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, not_, exists

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import matcher, resume_customizer, notifier, usage, rise_index, submitter, pipeline_runner
from app.services.sources import greenhouse, lever, rss_boards
from app.services import discovery_sources
from app.config import settings

router = APIRouter(tags=["pipeline"])


# --- Discovery (shared job pool, not per-user) ---

@router.post("/pipeline/discover")
def discover(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Pulls fresh postings into the shared job pool. Any logged-in user can
    trigger this — it's idempotent (duplicate postings are skipped)."""
    return pipeline_runner.run_discovery(db)


# --- Matching + tailoring for the current user ---

@router.post("/pipeline/match")
def match_and_tailor(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume before running matching.")

    has_active_profile = db.query(models.SearchProfile).filter_by(user_id=user.id, active=True).first()
    if not has_active_profile:
        raise HTTPException(status_code=400, detail="Add at least one active search profile first.")

    result = pipeline_runner.run_matching_for_user(db, user)
    return {
        "queued_application_ids": result["queued_application_ids"],
        "usage_limit_reached": result["usage_limit_reached"],
        "near_misses": result["near_misses"],
    }


# --- Applications list + approve/reject ---

def _to_out(app: models.Application, job: models.Job) -> schemas.ApplicationOut:
    return schemas.ApplicationOut(
        id=app.id, status=app.status or "pending_approval",
        matched_profile=app.matched_profile or "",
        match_score=app.match_score or 0,
        match_reason=app.match_reason or "",
        tailored_resume_path=app.tailored_resume_path or "",
        notes=app.notes or "",
        created_at=app.created_at or datetime.utcnow(),
        submitted_at=app.submitted_at,
        job_title=job.title or "", job_company=job.company or "",
        job_location=job.location or "", job_url=job.url or "",
    )


@router.get("/applications", response_model=list[schemas.ApplicationOut])
def list_applications(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(models.Application.user_id == user.id)
    if status:
        q = q.filter(models.Application.status == status)
    q = q.order_by(models.Application.match_score.desc())
    return [_to_out(app, job) for app, job in q.all()]


@router.get("/applications/{application_id}", response_model=schemas.ApplicationOut)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(models.Application.id == application_id, models.Application.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row, job = row
    return _to_out(app_row, job)


@router.post("/applications/{application_id}/approve")
def approve_application(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.status = "approved"
    app_row.status_updated_at = datetime.utcnow()
    db.commit()
    rise_index.award_points(db, user, "approve_match", "Reviewed and approved a match")
    return {"status": "approved"}


@router.post("/applications/{application_id}/reject")
def reject_application(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.status = "rejected"
    app_row.status_updated_at = datetime.utcnow()
    db.commit()
    rise_index.award_points(db, user, "review_match", "Reviewed a match")
    return {"status": "rejected"}


@router.post("/applications/{application_id}/mark-submitted")
def mark_submitted(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    """Confirms the application was actually sent -- the manual path.
    This is the real effort milestone the Rise Index measures response
    times from, and is also what auto-submit calls internally on a
    successful attempt, so both paths behave identically from here."""
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.status = "submitted"
    now = datetime.utcnow()
    app_row.status_updated_at = now
    app_row.submitted_at = now
    db.commit()
    rise_index.award_points(db, user, "mark_submitted", "Submitted an application")
    return {"status": "submitted"}


@router.get("/applications/{application_id}/auto-submit-eligible")
def check_auto_submit_eligible(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    """Lets the frontend decide whether to show the auto-submit button at
    all, without actually launching a browser."""
    row = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(models.Application.id == application_id, models.Application.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row, job = row

    if not settings.auto_submit_enabled:
        return {"eligible": False, "reason": "Auto-submit isn't enabled on this server yet."}
    if app_row.status != "approved":
        return {"eligible": False, "reason": "Only approved applications can be auto-submitted."}

    allowed, reason = submitter.is_supported_ats(job.url)
    return {"eligible": allowed, "reason": reason}


@router.post("/applications/{application_id}/auto-submit")
def auto_submit_application(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    """Attempts to actually fill and submit the application via
    Playwright. Guardrails, in order:
    1. Global settings.auto_submit_enabled kill-switch
    2. Application must already be human-approved
    3. Job URL must be on the ATS allowlist (Greenhouse/Lever only,
       LinkedIn/Indeed explicitly hard-blocked regardless of config)
    Any failure leaves the application in 'approved' with a note
    explaining what happened, rather than silently losing the match."""
    if not settings.auto_submit_enabled:
        raise HTTPException(status_code=503, detail="Auto-submit isn't enabled on this server yet.")

    row = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(models.Application.id == application_id, models.Application.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row, job = row

    if app_row.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved applications can be auto-submitted.")

    allowed, reason = submitter.is_supported_ats(job.url)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)

    name_parts = (user.full_name or "").split(" ", 1)
    candidate = {
        "first_name": name_parts[0] if name_parts else "",
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "full_name": user.full_name or "",
        "email": user.email,
        "phone": user.phone or "",
        "location": user.location or "",
        "linkedin_url": user.linkedin_url or "",
        "portfolio_url": user.portfolio_url or "",
    }

    result = submitter.submit_application(
        job.url, app_row.tailored_resume_path, candidate, actually_submit=True,
    )

    if result["status"] == "submitted":
        now = datetime.utcnow()
        app_row.status = "submitted"
        app_row.status_updated_at = now
        app_row.submitted_at = now
        app_row.notes = "Auto-submitted."
        db.commit()
        rise_index.award_points(db, user, "mark_submitted", "Submitted an application (auto-submit)")
        try:
            notifier.notify_submitted(user.notify_email or user.email, {
                "title": job.title, "company": job.company, "url": job.url,
            })
        except Exception:
            pass
        return {"status": "submitted"}

    # needs_manual_review or failed -- leave status as 'approved', record
    # what happened, and let the user know rather than losing the thread
    app_row.notes = f"Auto-submit: {result['detail']}"
    db.commit()
    return {"status": result["status"], "detail": result["detail"]}


@router.post("/applications/{application_id}/mark-interviewing")
def mark_interviewing(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.status = "interviewing"
    app_row.status_updated_at = datetime.utcnow()
    db.commit()
    # No points here — landing an interview is an outcome, not effort.
    # We still log the check-in for streak purposes only.
    rise_index.record_activity(db, user)
    return {"status": "interviewing"}


@router.post("/applications/{application_id}/mark-accepted")
def mark_accepted(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.status = "accepted"
    app_row.status_updated_at = datetime.utcnow()
    db.commit()
    # No points — an offer is an outcome, not effort. Streak check-in only.
    rise_index.record_activity(db, user)
    return {"status": "accepted"}


# --- Usage summary ---

@router.get("/usage", response_model=schemas.UsageOut)
def get_usage(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    limits = usage.limits_for(user)
    return schemas.UsageOut(
        tier="pro" if usage.is_pro(user) else "free",
        matches_used=usage.get_usage(db, user.id, "match"),
        matches_limit=limits["match"],
        tailored_resumes_used=usage.get_usage(db, user.id, "tailor_resume"),
        tailored_resumes_limit=limits["tailor_resume"],
        interview_preps_used=usage.get_usage(db, user.id, "interview_prep"),
        interview_preps_limit=limits["interview_prep"],
        onboarding_plans_used=usage.get_usage(db, user.id, "onboarding_plan"),
        onboarding_plans_limit=limits["onboarding_plan"],
        job_buddy_messages_used=usage.get_usage(db, user.id, "job_buddy_message"),
        job_buddy_messages_limit=limits["job_buddy_message"],
    )
