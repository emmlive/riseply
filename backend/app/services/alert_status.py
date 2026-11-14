"""Why didn't I get an alert? Answered from the app's own records, in plain
words, so nobody has to read server logs. Each check says what it found and,
when it is a problem, what to do about it. Nothing here sends anything."""
import json
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.config import settings

STALE_RUN = timedelta(hours=36)
STALE_TICK = timedelta(hours=3)
HEARTBEAT = "smart_alerts"


def record_tick(db: Session, result: dict, now: datetime | None = None) -> None:
    """One row each time the hourly alerts job runs, so 'is the hourly job running at
    all?' can be answered. Rows older than three days are dropped."""
    now = now or datetime.utcnow()
    db.add(models.ScheduledRunLog(run_type=HEARTBEAT, status="success", result_json=json.dumps(result),
                                  started_at=now, finished_at=now))
    db.query(models.ScheduledRunLog).filter(
        models.ScheduledRunLog.run_type == HEARTBEAT, models.ScheduledRunLog.started_at < now - timedelta(days=3)
    ).delete(synchronize_session=False)
    db.commit()


def _ago(then: datetime | None, now: datetime) -> str:
    if not then:
        return "never"
    mins = int((now - then).total_seconds() // 60)
    if mins < 90:
        return f"{max(mins, 1)} minutes ago"
    hours = mins // 60
    return f"{hours} hours ago" if hours < 48 else f"{hours // 24} days ago"


def _check(cid: str, ok: bool, title: str, detail: str, fix_href: str = "", fix_label: str = "", tip: bool = False) -> dict:
    return {"id": cid, "ok": ok, "tip": tip and not ok, "title": title, "detail": detail,
            "fix_href": fix_href, "fix_label": fix_label}


def build(db: Session, user: models.User, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    checks: list[dict] = []
    pref = user.notification_preference or "every_match"
    channel = user.notification_channel or "email"
    to = user.notify_email or user.email

    # --- the person's own setup
    has_resume = bool((user.resume_text or "").strip())
    checks.append(_check("resume", has_resume, "Your resume is on file",
                         "Riseply needs it to find and score jobs for you." if not has_resume else "Searches and scores use it.",
                         "/dashboard/resume", "Add your resume"))

    profiles = db.query(models.SearchProfile).filter_by(user_id=user.id, active=True).all()
    titled = [p for p in profiles if json.loads(p.titles or "[]")]
    checks.append(_check("search", bool(titled), "You have an active job search",
                         "No active search has a job title, so there is nothing to look for." if not titled
                         else f"Looking for: {', '.join(json.loads(titled[0].titles or '[]')[:3])}" + (f" and {len(titled) - 1} more search{'es' if len(titled) > 2 else ''}" if len(titled) > 1 else ""),
                         "/dashboard/profiles", "Set up a search"))

    checks.append(_check("preference", pref != "off", "Alerts are switched on",
                         "Your alerts are set to Off, so nothing is ever sent." if pref == "off"
                         else {"smart": "Smart alerts: standout matches right away, the rest in one daily digest.",
                               "every_match": "An alert for every match.", "daily_digest": "One digest a day."}.get(pref, "On."),
                         "/dashboard/profile", "Change alert setting"))

    # --- email
    if channel in ("email", "both"):
        recent = db.query(models.EmailLog).filter(
            models.EmailLog.to_addr.in_([to, user.email]), models.EmailLog.created_at > now - timedelta(days=14)
        ).order_by(models.EmailLog.created_at.desc()).limit(10).all()
        if not settings.resend_api_key:
            checks.append(_check("email", False, "Email can be sent",
                                 "Email is not set up on the server (no email service key), so no email can leave. Add RESEND_API_KEY on Render."))
        elif any(r.status == "failed" for r in recent[:3]):
            bad = next(r for r in recent if r.status == "failed")
            checks.append(_check("email", False, "Email can be sent", f"The last attempt to {to} failed: {(bad.error or 'unknown error')[:160]}"))
        elif any(r.status == "skipped" for r in recent[:3]):
            checks.append(_check("email", False, "Email can be sent", "Recent emails were skipped because email is not configured on the server."))
        else:
            sent = next((r for r in recent if r.status == "sent"), None)
            checks.append(_check("email", True, f"Email goes to {to}",
                                 f"Last email sent {_ago(sent.created_at, now)}." if sent else "Nothing sent yet. Use the test button to confirm it arrives."))
    else:
        checks.append(_check("email", True, "Email", "Your alert channel is not email."))

    # --- Discord
    conn = db.query(models.DiscordConnection).filter_by(user_id=user.id).first()
    if not conn:
        checks.append(_check("discord", False, "Discord is connected", "Not connected. Paste a Discord webhook to get alerts there too.",
                             "/dashboard/profile", "Connect Discord", tip=True))
    elif not conn.enabled:
        checks.append(_check("discord", False, "Discord is connected", conn.last_error or "Discord is switched off for your account.",
                             "/dashboard/profile", "Reconnect Discord"))
    elif not conn.matches_enabled:
        checks.append(_check("discord", False, "Discord gets job alerts",
                             "Discord is connected, but job-match alerts are switched off for it. It only sends practice nudges right now.",
                             "/dashboard/profile", "Turn on job matches"))
    elif conn.consecutive_failures:
        checks.append(_check("discord", False, "Discord gets job alerts", f"Delivery is failing: {conn.last_error or 'unknown error'}",
                             "/dashboard/profile", "Check Discord"))
    else:
        checks.append(_check("discord", True, "Discord gets job alerts",
                             f"Last delivered {_ago(conn.last_success_at, now)}." if conn.last_success_at else "Connected. Nothing delivered yet."))

    # --- the engine: search, match, alert
    run = db.query(models.ScheduledRunLog).filter_by(run_type="scheduled_run").order_by(models.ScheduledRunLog.started_at.desc()).first()
    if not run:
        checks.append(_check("daily_search", False, "The daily job search runs",
                             "It has never run. In GitHub: Actions, Daily job matching, Run workflow. If it fails, check the BACKEND_URL and CRON_SECRET secrets."))
    elif run.status == "failed":
        checks.append(_check("daily_search", False, "The daily job search runs",
                             f"The last run ({_ago(run.started_at, now)}) failed: {(run.error or 'no detail')[:160]}"))
    elif now - (run.finished_at or run.started_at) > STALE_RUN:
        checks.append(_check("daily_search", False, "The daily job search runs",
                             f"It last ran {_ago(run.finished_at or run.started_at, now)}. It should run every day. Check the Daily job matching workflow in GitHub Actions."))
    else:
        checks.append(_check("daily_search", True, "The daily job search runs", f"Last ran {_ago(run.finished_at or run.started_at, now)}."))

    if pref == "smart":
        tick = db.query(models.ScheduledRunLog).filter_by(run_type=HEARTBEAT).order_by(models.ScheduledRunLog.started_at.desc()).first()
        if not tick or now - tick.started_at > STALE_TICK:
            checks.append(_check("hourly", False, "The hourly alert job runs",
                                 ("It has not run yet." if not tick else f"It last ran {_ago(tick.started_at, now)}.")
                                 + " In GitHub: Actions, Smart alerts, Run workflow, and check the BACKEND_URL and CRON_SECRET secrets."))
        else:
            checks.append(_check("hourly", True, "The hourly alert job runs", f"Last ran {_ago(tick.started_at, now)}."))

    found_24h = db.query(func.count(models.Job.id)).filter(models.Job.discovered_at > now - timedelta(hours=24), models.Job.source != "imported").scalar() or 0
    found_7d = db.query(func.count(models.Job.id)).filter(models.Job.discovered_at > now - timedelta(days=7), models.Job.source != "imported").scalar() or 0
    checks.append(_check("jobs_found", found_7d > 0, "New jobs are being found",
                         "No new jobs were found in the last 7 days. The job sources may not be set up (Admin, Source report)." if not found_7d
                         else f"{found_24h} new jobs in the last day, {found_7d} in the last week."))

    mine_7d = db.query(func.count(models.Application.id)).filter(
        models.Application.user_id == user.id, models.Application.created_at > now - timedelta(days=7),
        models.Application.deleted_at.is_(None), models.Application.status != "submitted").scalar() or 0
    floor = user.notification_min_score or 0
    if mine_7d:
        checks.append(_check("matches", True, "Jobs are matching you", f"{mine_7d} new match{'es' if mine_7d != 1 else ''} in the last 7 days."))
    elif found_7d:
        checks.append(_check("matches", False, "Jobs are matching you",
                             "Jobs were found, but none matched your search" + (f" at your minimum score of {floor}" if floor else "") +
                             ". Add related job titles or lower the minimum match score to about 65.",
                             "/dashboard/profiles", "Widen your search"))
    else:
        checks.append(_check("matches", False, "Jobs are matching you", "Nothing to match yet, because no new jobs were found.", tip=True))

    last_alert = db.query(func.max(models.Application.alerted_at)).filter(models.Application.user_id == user.id).scalar()
    problems = [c for c in checks if not c["ok"] and not c["tip"]]
    if not problems:
        headline = "Everything is set up. You will hear from us when a job fits."
    else:
        headline = f"{len(problems)} thing{'s are' if len(problems) != 1 else ' is'} stopping your alerts."
    return {
        "headline": headline, "ok": not problems, "checks": checks,
        "last_digest": user.last_digest_sent_at.isoformat() + "Z" if user.last_digest_sent_at else None,
        "last_instant": last_alert.isoformat() + "Z" if last_alert else None,
    }
