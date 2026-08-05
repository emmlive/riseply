"""
The core "find matches for this user" logic, extracted so both the
manual per-user endpoint (POST /pipeline/match, triggered by a click)
and the scheduled batch job (triggered externally on a schedule) run the
EXACT same code path. Two implementations of this would drift apart the
first time either one got a bugfix.
"""
import json
from datetime import datetime
from sqlalchemy import not_
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from fastapi import HTTPException

from app import models
from app.services import matcher, resume_customizer, notifier, usage, rise_index
from app.services.sources import greenhouse, lever, rss_boards
from app.services import discovery_sources


def run_discovery(db: Session) -> dict:
    """Pulls fresh postings into the shared job pool.

    Uses a database-level INSERT ... ON CONFLICT DO NOTHING rather than a
    manual "check if it exists, then insert" loop. The manual version had
    a real gap: it only committed once at the end of the whole loop, so
    two jobs with the same (source, external_id) landing in the same
    batch -- or two near-simultaneous requests racing each other, since
    this runs in a thread pool -- could both pass the "does this exist"
    check before either had committed, then crash into each other's
    INSERT with a UniqueViolation. Postgres and SQLite both resolve
    ON CONFLICT atomically at the database level, which closes that gap
    regardless of the exact interleaving.
    """
    raw_jobs = []
    raw_jobs += greenhouse.fetch_all(discovery_sources.GREENHOUSE_COMPANIES)
    raw_jobs += lever.fetch_all(discovery_sources.LEVER_COMPANIES)
    raw_jobs += rss_boards.fetch_all(discovery_sources.RSS_JOB_FEEDS)

    if not raw_jobs:
        return {"discovered": 0, "new": 0}

    insert_fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert

    new_count = 0
    for j in raw_jobs:
        stmt = insert_fn(models.Job).values(
            source=j["source"], external_id=j["external_id"], company=j["company"],
            title=j["title"], location=j["location"], url=j["url"],
            description=j["description"],
        ).on_conflict_do_nothing(index_elements=["source", "external_id"])
        result = db.execute(stmt)
        if result.rowcount > 0:
            new_count += 1
    db.commit()
    return {"discovered": len(raw_jobs), "new": new_count}


def run_matching_for_user(db: Session, user: models.User) -> dict:
    """Returns {"queued_application_ids": [...], "usage_limit_reached": bool,
    "skipped_reason": str | None}. Never raises for expected "nothing to
    do" cases (no resume, no active profiles) -- those come back as a
    skipped_reason instead, since a batch job processing many users needs
    to move on to the next one rather than crash the whole run."""
    if not user.resume_text.strip():
        return {"queued_application_ids": [], "usage_limit_reached": False, "skipped_reason": "no_resume"}

    profiles_rows = db.query(models.SearchProfile).filter_by(user_id=user.id, active=True).all()
    if not profiles_rows:
        return {"queued_application_ids": [], "usage_limit_reached": False, "skipped_reason": "no_active_profiles"}

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
            continue

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
            pass
        queued.append(application.id)

    rise_index.award_points(db, user, "run_search", "Ran a job search")
    return {"queued_application_ids": queued, "usage_limit_reached": limit_hit, "skipped_reason": None}
