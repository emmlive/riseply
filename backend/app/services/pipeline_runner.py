"""
The core "find matches for this user" logic, extracted so both the
manual per-user endpoint (POST /pipeline/match, triggered by a click)
and the scheduled batch job (triggered externally on a schedule) run the
EXACT same code path. Two implementations of this would drift apart the
first time either one got a bugfix.
"""
import json
from datetime import datetime, timedelta
from sqlalchemy import not_
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from fastapi import HTTPException

from app import models
from app.services import matcher, resume_customizer, notifier, usage, rise_index, sms
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


def run_matching_for_user(db: Session, user: models.User, max_jobs: int | None = None) -> dict:
    """Returns {"queued_application_ids": [...], "usage_limit_reached": bool,
    "skipped_reason": str | None}. Never raises for expected "nothing to
    do" cases (no resume, no active profiles) -- those come back as a
    skipped_reason instead, since a batch job processing many users needs
    to move on to the next one rather than crash the whole run.

    max_jobs bounds how many unseen jobs get scored in this single call.
    Every job scores via a real Claude API call, sequentially -- with no
    cap, one click of the "Find new matches" button could mean hundreds
    of sequential API calls in a single blocking HTTP request (everything
    up to the user's monthly limit, which for an admin account is
    unbounded), taking minutes with no way for the UI to show real
    progress in between. The interactive endpoint (POST /pipeline/match)
    passes a small cap so a click returns in a reasonable time; the
    scheduled batch job (POST /internal/scheduled-run) passes none, so it
    still works through the full backlog overnight. hit_job_cap in the
    return value tells the caller there's more left uncapped by usage --
    worth surfacing differently from "genuinely out of jobs to score."
    """
    if not user.resume_text.strip():
        return {"queued_application_ids": [], "usage_limit_reached": False, "skipped_reason": "no_resume", "near_misses": [], "hit_job_cap": False}

    profiles_rows = db.query(models.SearchProfile).filter_by(user_id=user.id, active=True).all()
    if not profiles_rows:
        return {"queued_application_ids": [], "usage_limit_reached": False, "skipped_reason": "no_active_profiles", "near_misses": [], "hit_job_cap": False}

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
    already_scored_subq = db.query(models.ScoredJob.job_id).filter(
        models.ScoredJob.user_id == user.id
    ).subquery()
    unseen_jobs = db.query(models.Job).filter(
        not_(models.Job.id.in_(already_applied_subq)),
        not_(models.Job.id.in_(already_scored_subq)),
    ).all()

    hit_job_cap = False
    if max_jobs is not None and len(unseen_jobs) > max_jobs:
        hit_job_cap = True
        unseen_jobs = unseen_jobs[:max_jobs]

    queued = []
    near_miss_candidates = []  # (score, {title, company, url, score, reason, matched_profile})
    NEAR_MISS_CAP = 3
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
        except Exception as e:
            # This was previously silent -- caught, refunded, skipped,
            # with zero trace of *why*. That made a real failure (bad
            # API key, rate limit, model returning malformed JSON) look
            # identical in the logs to "nothing matched," which is
            # exactly the ambiguity that made this bug hard to diagnose
            # from the outside. Printed so it shows up in Render's log
            # stream without needing a new logging dependency.
            print(f"[matcher] scoring failed for job {job_row.id} ({job_row.company} — {job_row.title}): {e}")
            usage.decrement(db, user.id, "match", 1)
            continue

        # Mark this job as evaluated for this user regardless of outcome,
        # so a future run doesn't re-score (and re-bill quota for) it
        # again just because it fell short this time. ON CONFLICT DO
        # NOTHING guards the same race the discovery insert guards
        # against -- two near-simultaneous runs for the same user
        # shouldn't crash into each other's insert.
        insert_fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
        db.execute(
            insert_fn(models.ScoredJob)
            .values(user_id=user.id, job_id=job_row.id)
            .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
        )
        db.commit()

        if not best["meets_threshold"]:
            # Track the closest-scoring misses as we go, capped at
            # NEAR_MISS_CAP, so a search that finds nothing real still
            # has something concrete to show -- "nothing hit your bar,
            # but here's what came closest" rather than a cold empty
            # state that looks like the tool didn't do anything.
            near_miss_candidates.append((best["score"], {
                "title": job_row.title, "company": job_row.company, "url": job_row.url,
                "score": best["score"], "reason": best["reason"],
                "matched_profile": best["profile_name"],
            }))
            near_miss_candidates.sort(key=lambda t: t[0], reverse=True)
            near_miss_candidates = near_miss_candidates[:NEAR_MISS_CAP]
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
        resume_bytes = None
        try:
            usage.check_and_increment(db, user, "tailor_resume", 1)
            job["matched_profile"] = best["profile_name"]
            job["match_score"] = best["score"]
            resume_path, resume_bytes, rationale = resume_customizer.customize_for_job(
                user.id, user.resume_text, job, application.id
            )
            application.tailored_resume_path = resume_path
            application.tailored_resume_data = resume_bytes
            application.tailoring_rationale = rationale
            db.commit()
        except HTTPException:
            application.notes = "Resume not tailored — monthly tailoring limit reached; using base resume."
            db.commit()
        except Exception as e:
            print(f"[resume_customizer] tailoring failed for application {application.id}: {e}")
            usage.decrement(db, user.id, "tailor_resume", 1)
            application.notes = "Resume tailoring failed this run — using base resume. You can retry from the dashboard later."
            db.commit()

        notify_addr = user.notify_email or user.email
        preference = user.notification_preference or "every_match"
        channel = user.notification_channel or "email"
        clears_threshold = best["score"] >= (user.notification_min_score or 0)
        # "off" -> never notify. "daily_digest" -> never notify HERE; the
        # digest job (send_daily_digests, run once a day) picks up every
        # Application created since the user's last digest, so this
        # match still gets surfaced, just batched instead of immediate.
        # Applies the same way regardless of whether this run came from
        # a manual click or the scheduled job -- one preference, one
        # behavior, not a confusing split by trigger source.
        if preference == "every_match" and clears_threshold:
            job_notify = {**job, "matched_profile": best["profile_name"], "match_score": best["score"],
                          "match_reason": best["reason"]}
            if channel in ("email", "both"):
                try:
                    notifier.notify_new_match(notify_addr, job_notify, application.id, resume_path, resume_bytes)
                except Exception as e:
                    print(f"[pipeline] New match email failed for user {user.id}, application {application.id}: {e}")
            # sms_consent is enforced at the point channel gets set
            # (routers/me.py) -- checked again here as defense in depth,
            # not because it should ever be false while channel includes
            # sms, but a stale/directly-edited row shouldn't be able to
            # bypass consent just because this check was skipped.
            if channel in ("sms", "both") and user.sms_consent:
                try:
                    sms.notify_new_match_sms(user.phone, job_notify)
                except Exception as e:
                    print(f"[pipeline] New match SMS failed for user {user.id}, application {application.id}: {e}")
        queued.append(application.id)

    # Near-misses are only worth surfacing when nothing real was found --
    # if there are genuine matches to review, a "here's what almost
    # worked" list would just be noise.
    near_misses = [c[1] for c in near_miss_candidates] if not queued else []

    rise_index.award_points(db, user, "run_search", "Ran a job search")
    return {
        "queued_application_ids": queued, "usage_limit_reached": limit_hit,
        "skipped_reason": None, "near_misses": near_misses, "hit_job_cap": hit_job_cap,
    }


def send_daily_digests(db: Session) -> dict:
    """For every user on notification_preference='daily_digest', emails
    one summary of every match queued since their last digest -- rather
    than the immediate per-match email 'every_match' users get. Queried
    per-user against last_digest_sent_at (not a fixed 24h window), so
    this stays correct regardless of when in the day matches actually
    landed -- manual 'Find new matches' clicks happen at arbitrary
    times, not just during the scheduled run.

    Meant to run once daily, after the scheduled matching run, via
    POST /internal/send-digests -- same secret-gated, externally-
    triggered pattern as scheduled-run and culture-bot-run."""
    users = db.query(models.User).filter_by(notification_preference="daily_digest").all()
    sent = 0

    for user in users:
        since = user.last_digest_sent_at or (datetime.utcnow() - timedelta(days=1))
        rows = db.query(models.Application, models.Job).join(
            models.Job, models.Application.job_id == models.Job.id
        ).filter(
            models.Application.user_id == user.id,
            models.Application.created_at > since,
            models.Application.match_score >= (user.notification_min_score or 0),
        ).all()

        matches = [
            {
                "title": job.title, "company": job.company, "location": job.location,
                "match_score": app_row.match_score, "match_reason": app_row.match_reason, "url": job.url,
            }
            for app_row, job in rows
        ]

        if matches:
            channel = user.notification_channel or "email"
            if channel in ("email", "both"):
                try:
                    notifier.notify_digest(user.notify_email or user.email, matches)
                    sent += 1
                except Exception as e:
                    print(f"[pipeline] Digest email failed for user {user.id}: {e}")
            if channel in ("sms", "both") and user.sms_consent:
                try:
                    sms.notify_digest_sms(user.phone, len(matches))
                    sent += 1
                except Exception as e:
                    print(f"[pipeline] Digest SMS failed for user {user.id}: {e}")

        user.last_digest_sent_at = datetime.utcnow()
        db.commit()

    return {"digests_sent": sent}
