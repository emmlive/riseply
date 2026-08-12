import json
import os
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

    result = pipeline_runner.run_matching_for_user(db, user, max_jobs=settings.manual_match_run_job_cap)
    return {
        "queued_application_ids": result["queued_application_ids"],
        "usage_limit_reached": result["usage_limit_reached"],
        "near_misses": result["near_misses"],
        "hit_job_cap": result["hit_job_cap"],
    }


@router.get("/pipeline/near-misses", response_model=list[schemas.NearMissOut])
def get_near_misses(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The current user's persisted near-misses (see models.NearMissResult)
    -- lets the dashboard show 'what came closest last time' on a fresh
    page load, not only right after a POST /pipeline/match response.
    Empty list is a valid, correct answer (no run yet, or the last run
    found a real match / genuinely nothing close), not an error case.
    """
    rows = db.query(models.NearMissResult, models.Job).join(
        models.Job, models.NearMissResult.job_id == models.Job.id
    ).filter(models.NearMissResult.user_id == user.id).order_by(
        models.NearMissResult.score.desc()
    ).all()

    return [
        schemas.NearMissOut(
            title=job.title, company=job.company, url=job.url,
            score=nm.score, reason=nm.reason, matched_profile=nm.matched_profile,
            salary_min=job.salary_min, salary_max=job.salary_max,
            salary_currency=job.salary_currency or "", salary_is_predicted=bool(job.salary_is_predicted),
            location_mismatch=bool(nm.location_mismatch),
        )
        for nm, job in rows
    ]


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
        organization_id=app.organization_id,
        organization_logo_url=(app.organization.logo_url or "") if app.organization else "",
        tailoring_rationale=app.tailoring_rationale or "",
        has_tailored_resume_data=bool(app.tailored_resume_data),
        salary_min=job.salary_min, salary_max=job.salary_max,
        salary_currency=job.salary_currency or "", salary_is_predicted=bool(job.salary_is_predicted),
        is_archived=bool(app.is_archived), archived_at=app.archived_at,
    )


@router.get("/applications", response_model=list[schemas.ApplicationOut])
def list_applications(
    status: str | None = None,
    archived: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """archived=False (the default) excludes archived applications --
    every existing status tab (All/Awaiting review/Approved/etc) keeps
    working exactly as before with zero frontend changes required,
    since archiving something now makes it disappear from all of them
    automatically. archived=True is the inverse -- shows ONLY archived
    applications, for a dedicated Archived view.
    """
    q = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(
        models.Application.user_id == user.id,
        models.Application.is_archived == archived,
    )
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


@router.get("/applications/{application_id}/tailored-resume")
def download_tailored_resume(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Serves the tailored resume from the database, not the filesystem
    -- Render's web service disk is ephemeral and doesn't survive a
    redeploy, so this document has to live in Postgres to actually
    persist. Replaces the old /files/tailored_resumes/... static mount,
    which silently 404'd for anything generated before the most recent
    deploy."""
    from fastapi.responses import Response

    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    if not app_row.tailored_resume_data:
        raise HTTPException(status_code=404, detail="No tailored resume available for this application yet.")

    filename = app_row.tailored_resume_path or "tailored_resume.docx"
    return Response(
        content=app_row.tailored_resume_data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/applications/{application_id}/retailor", response_model=schemas.ApplicationOut)
def retailor_resume(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Regenerates the tailored resume for an existing application --
    mainly for applications whose original tailoring predates the
    switch to storing the document in Postgres (see the commit fixing
    the ephemeral-disk 404 bug) and so have a filename on record but no
    actual data to serve. Also useful any time someone's updated their
    base resume and wants this specific application's tailoring
    refreshed against the new version. Metered the same as the
    original tailoring -- this is a real Claude call, not free."""
    row = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(models.Application.id == application_id, models.Application.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row, job = row

    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume before re-tailoring.")

    usage.check_and_increment(db, user, "tailor_resume", 1)
    try:
        job_dict = {
            "title": job.title, "company": job.company,
            "location": job.location, "url": job.url, "description": job.description,
        }
        filename, docx_bytes, rationale = resume_customizer.customize_for_job(
            user.id, user.resume_text, job_dict, app_row.id
        )
    except Exception:
        usage.decrement(db, user.id, "tailor_resume", 1)
        raise HTTPException(status_code=502, detail="Couldn't re-tailor this resume right now — try again shortly.")

    app_row.tailored_resume_path = filename
    app_row.tailored_resume_data = docx_bytes
    app_row.tailoring_rationale = rationale
    db.commit()
    db.refresh(app_row)
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


# --- Archivable pattern (request-handling half -- see models.Application's
# is_archived/archived_at columns for the storage half). Any status --
# rejected, accepted, or still pending -- can be archived; this is
# purely "get this out of my default view," independent of and does
# not change the underlying status. Copy this pair verbatim onto any
# future model that adopts the same pattern. ---

@router.post("/applications/{application_id}/archive")
def archive_application(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.is_archived = True
    app_row.archived_at = datetime.utcnow()
    db.commit()
    return {"status": "archived"}


@router.post("/applications/{application_id}/unarchive")
def unarchive_application(
    application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row.is_archived = False
    app_row.archived_at = None
    db.commit()
    return {"status": "unarchived"}


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
    """Lets the frontend decide whether to show the auto-fill/auto-submit
    buttons at all, without actually launching a browser. Same
    eligibility criteria for both -- they differ only in whether the
    final submit click happens, not in what's allowed to attempt it."""
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


def _build_candidate_dict(user: models.User) -> dict:
    name_parts = (user.full_name or "").split(" ", 1)
    return {
        "first_name": name_parts[0] if name_parts else "",
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "full_name": user.full_name or "",
        "email": user.email,
        "phone": user.phone or "",
        "location": user.location or "",
        "linkedin_url": user.linkedin_url or "",
        "portfolio_url": user.portfolio_url or "",
    }


def _run_submitter(app_row: models.Application, job: models.Job, user: models.User, actually_submit: bool) -> dict:
    """Shared by auto-submit and auto-fill -- same guardrails, same
    browser automation, the only difference is whether the final submit
    click happens. submit_application() itself already stops one step
    short of submitting when actually_submit=False (see submitter.py),
    so this is just the shared plumbing around that call: building the
    candidate dict and materializing the tailored resume as a temp file
    for Playwright to upload, since it needs a real file on disk that
    only has to survive this one request."""
    candidate = _build_candidate_dict(user)

    resume_file_path = ""
    if app_row.tailored_resume_data:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.write(app_row.tailored_resume_data)
        tmp.close()
        resume_file_path = tmp.name

    try:
        return submitter.submit_application(job.url, resume_file_path, candidate, actually_submit=actually_submit)
    finally:
        if resume_file_path:
            os.unlink(resume_file_path)


def _get_approved_application_for_submit(db: Session, application_id: int, user: models.User):
    if not settings.auto_submit_enabled:
        raise HTTPException(status_code=503, detail="Auto-submit isn't enabled on this server yet.")

    row = db.query(models.Application, models.Job).join(
        models.Job, models.Application.job_id == models.Job.id
    ).filter(models.Application.id == application_id, models.Application.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    app_row, job = row

    if app_row.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved applications can be auto-filled or auto-submitted.")

    allowed, reason = submitter.is_supported_ats(job.url)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)

    return app_row, job


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
    app_row, job = _get_approved_application_for_submit(db, application_id, user)
    result = _run_submitter(app_row, job, user, actually_submit=True)

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
        except Exception as e:
            print(f"[pipeline] Submission confirmation email failed for user {user.id}, application {application_id}: {e}")
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
