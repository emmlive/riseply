import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, not_, exists

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import matcher, resume_customizer, notifier, usage, rise_index
from app.services.sources import greenhouse, lever, rss_boards
from app.services import discovery_sources
from app.config import settings

router = APIRouter(tags=["pipeline"])


# --- Discovery (shared job pool, not per-user) ---

@router.post("/pipeline/discover")
def discover(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Pulls fresh postings into the shared job pool. Any logged-in user can
    trigger this — it's idempotent (duplicate postings are skipped)."""
    raw_jobs = []
    raw_jobs += greenhouse.fetch_all(discovery_sources.GREENHOUSE_COMPANIES)
    raw_jobs += lever.fetch_all(discovery_sources.LEVER_COMPANIES)
    raw_jobs += rss_boards.fetch_all(discovery_sources.RSS_JOB_FEEDS)

    new_count = 0
    for j in raw_jobs:
        existing = db.query(models.Job).filter_by(
            source=j["source"], external_id=j["external_id"]
        ).first()
        if existing:
            continue
        db.add(models.Job(
            source=j["source"], external_id=j["external_id"], company=j["company"],
            title=j["title"], location=j["location"], url=j["url"],
            description=j["description"],
        ))
        new_count += 1
    db.commit()
    return {"discovered": len(raw_jobs), "new": new_count}


# --- Matching + tailoring for the current user ---

@router.post("/pipeline/match")
def match_and_tailor(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume before running matching.")

    profiles_rows = db.query(models.SearchProfile).filter_by(user_id=user.id, active=True).all()
    if not profiles_rows:
        raise HTTPException(status_code=400, detail="Add at least one active search profile first.")

    profiles = [{
        "name": p.name,
        "titles": json.loads(p.titles),
        "locations": json.loads(p.locations),
        "seniority": json.loads(p.seniority),
        "min_match_score": p.min_match_score,
        "exclude_companies": json.loads(p.exclude_companies),
        "keywords_required": json.loads(p.keywords_required),
        "keywords_excluded": json.loads(p.keywords_excluded),
        "active": p.active,
    } for p in profiles_rows]

    # Jobs this user hasn't already got an Application for
    already_applied_subq = db.query(models.Application.job_id).filter(
        models.Application.user_id == user.id
    ).subquery()
    unseen_jobs = db.query(models.Job).filter(
        not_(models.Job.id.in_(already_applied_subq))
    ).all()

    queued = []
    limit_hit = False

    for job_row in unseen_jobs:
        try:
            usage.check_and_increment(db, user, "match", 1)
        except HTTPException:
            limit_hit = True
            break

        job = {
            "title": job_row.title, "company": job_row.company,
            "location": job_row.location, "url": job_row.url,
            "description": job_row.description,
        }
        try:
            best = matcher.best_profile_match(job, user.resume_text, profiles)
        except Exception:
            usage.decrement(db, user.id, "match", 1)
            continue  # skip this job, don't let one API hiccup kill the whole batch

        if not best["meets_threshold"]:
            continue

        application = models.Application(
            user_id=user.id, job_id=job_row.id,
            matched_profile=best["profile_name"], match_score=best["score"],
            match_reason=best["reason"], status="pending_approval",
        )
        db.add(application)
        db.commit()
        db.refresh(application)

        resume_path = ""
        try:
            usage.check_and_increment(db, user, "tailor_resume", 1)
            job["matched_profile"] = best["profile_name"]
            job["match_score"] = best["score"]
            resume_path = resume_customizer.customize_for_job(
                user.id, user.resume_text, job, application.id
            )
            application.tailored_resume_path = resume_path
            db.commit()
        except HTTPException:
            application.notes = "Resume not tailored — monthly tailoring limit reached; using base resume."
            db.commit()
        except Exception:
            usage.decrement(db, user.id, "tailor_resume", 1)
            application.notes = "Resume tailoring failed this run — using base resume. You can retry from the dashboard later."
            db.commit()

        notify_addr = user.notify_email or user.email
        try:
            notifier.notify_new_match(
                notify_addr,
                {**job, "matched_profile": best["profile_name"], "match_score": best["score"],
                 "match_reason": best["reason"]},
                application.id, resume_path,
            )
        except Exception:
            pass  # notification is a side effect — a failure here shouldn't lose the match itself
        queued.append(application.id)

    rise_index.award_points(db, user, "run_search", "Ran a job search")
    return {"queued_application_ids": queued, "usage_limit_reached": limit_hit}


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
    """Confirms the application was actually sent — a manual step for now
    since auto-submit isn't wired up yet. This is the real effort
    milestone the Rise Index measures response times from."""
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
