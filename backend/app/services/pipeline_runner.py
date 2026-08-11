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
from app.services.sources import greenhouse, lever, rss_boards, adzuna
from app.services import discovery_sources
from app.config import settings


def _collect_active_search_titles(db: Session) -> list[str]:
    """Every distinct job title across every user's ACTIVE search
    profiles, shared-pool-wide (not per-user -- discovery itself isn't
    tenant-scoped, only matching is). This is what makes discovery follow
    whatever industries people are actually searching for instead of
    being capped at a hand-picked company list: a user whose profile
    targets "Compliance Analyst" or "Store Manager" or "ICU Nurse" makes
    that title a live Adzuna query the very next discovery run, with zero
    code changes needed for that industry.
    """
    rows = db.query(models.SearchProfile.titles).filter_by(active=True).all()
    seen_lower = set()
    titles = []
    for (titles_json,) in rows:
        try:
            for t in json.loads(titles_json or "[]"):
                t = (t or "").strip()
                if t and t.lower() not in seen_lower:
                    seen_lower.add(t.lower())
                    titles.append(t)
        except (json.JSONDecodeError, TypeError):
            continue  # a malformed row shouldn't take down discovery for everyone else
    return titles


def _select_keyword_rotation(keywords: list[str], max_per_run: int) -> list[str]:
    """Bounds how many distinct keywords get queried in a single run
    (see adzuna_max_keywords_per_run's docstring in config.py for why),
    while still covering every keyword over time rather than always
    querying the same first N and starving the rest. Stateless by
    design -- no new table to track "which keywords were queried
    last" -- deterministically rotates the starting offset by day of
    year instead, so running this repeatedly across days works through
    the full list, and running it repeatedly within the same day is
    harmless idempotent overlap rather than a bug.
    """
    if len(keywords) <= max_per_run:
        return keywords
    keywords_sorted = sorted(keywords, key=str.lower)
    n = len(keywords_sorted)
    offset = datetime.utcnow().timetuple().tm_yday % n
    return [keywords_sorted[(offset + i) % n] for i in range(max_per_run)]


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
    gh_jobs = greenhouse.fetch_all(discovery_sources.GREENHOUSE_COMPANIES)
    lever_jobs = lever.fetch_all(discovery_sources.LEVER_COMPANIES)
    rss_jobs = rss_boards.fetch_all(discovery_sources.RSS_JOB_FEEDS)
    raw_jobs += gh_jobs
    raw_jobs += lever_jobs
    raw_jobs += rss_jobs

    # Adzuna: general, all-industries keyword search -- driven by
    # whatever titles are actually in people's active search profiles
    # right now, not a fixed list. See _collect_active_search_titles()
    # and _select_keyword_rotation() above for why. No-ops cleanly if
    # ADZUNA_APP_ID/ADZUNA_APP_KEY aren't configured (see adzuna.py).
    search_titles = _collect_active_search_titles(db)
    keywords_this_run = _select_keyword_rotation(search_titles, settings.adzuna_max_keywords_per_run)
    print(f"[discovery] {len(search_titles)} distinct active search-profile title(s) total, "
          f"{len(keywords_this_run)} selected for Adzuna this run")
    adzuna_jobs = adzuna.fetch_by_keywords(keywords_this_run)
    raw_jobs += adzuna_jobs

    print(f"[discovery] raw postings this run -- greenhouse: {len(gh_jobs)}, lever: {len(lever_jobs)}, "
          f"rss: {len(rss_jobs)}, adzuna: {len(adzuna_jobs)}, total: {len(raw_jobs)}")

    if not raw_jobs:
        return {"discovered": 0, "new": 0}

    insert_fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert

    new_count = 0
    for j in raw_jobs:
        stmt = insert_fn(models.Job).values(
            source=j["source"], external_id=j["external_id"], company=j["company"],
            title=j["title"], location=j["location"], url=j["url"],
            description=j["description"],
            # .get() rather than direct indexing -- only the Adzuna
            # source populates these (see adzuna.py); Greenhouse/Lever/
            # RSS job dicts simply don't have these keys at all, and
            # should insert with "no salary data" rather than a KeyError.
            salary_min=j.get("salary_min"), salary_max=j.get("salary_max"),
            salary_currency=j.get("salary_currency", ""),
            salary_is_predicted=j.get("salary_is_predicted", False),
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
    # ORDER BY discovered_at DESC is load-bearing, not cosmetic: without
    # it, this query returns rows in whatever order Postgres feels like
    # (effectively insertion/id order in practice), and greenhouse.py's
    # ~2,800-job backlog -- inserted every run BEFORE adzuna.py's much
    # smaller, keyword-driven results -- permanently sits at the front
    # of that order. A capped run (max_jobs=25 on the interactive
    # "Find new matches" button) would then need on the order of a
    # hundred clicks before ever reaching a single Adzuna row, no
    # matter how many fresh, well-targeted postings Adzuna just found.
    # Newest-first means a click always sees this run's freshest finds
    # (across every source) before working backward into the old
    # backlog -- the nightly scheduled job (max_jobs=None) still clears
    # the full backlog regardless of order, so nothing is lost, just
    # reprioritized for the interactive, capped case.
    unseen_jobs = db.query(models.Job).filter(
        not_(models.Job.id.in_(already_applied_subq)),
        not_(models.Job.id.in_(already_scored_subq)),
    ).order_by(models.Job.discovered_at.desc()).all()

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
            "salary_min": job_row.salary_min, "salary_max": job_row.salary_max,
            "salary_currency": job_row.salary_currency, "salary_is_predicted": job_row.salary_is_predicted,
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
                "salary_min": job_row.salary_min, "salary_max": job_row.salary_max,
                "salary_currency": job_row.salary_currency, "salary_is_predicted": job_row.salary_is_predicted,
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
                "salary_min": job.salary_min, "salary_max": job.salary_max,
                "salary_currency": job.salary_currency, "salary_is_predicted": job.salary_is_predicted,
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
