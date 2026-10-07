"""Discord 'keep your momentum' notifications, delivered through a webhook
the user creates in their own channel and pastes into Riseply.

Safety properties worth keeping in mind when editing this file:
  * The webhook URL is user-supplied and we make a server-side request to
    it, so it is matched against a STRICT allow-list pattern (discord.com
    webhooks only) before it is ever stored or used, and requests never
    follow redirects. That is what keeps this from being an SSRF vector.
  * Message text can include model output and user-typed strings (target
    role), so every payload sets allowed_mentions to none and neutralizes
    @everyone/@here -- nothing we send can ping anyone.
  * The URL is a credential for one channel: stored encrypted, never
    returned by the API, never logged.
  * Delivery is best-effort. A failing webhook never breaks the feature
    that triggered it, and repeated failures switch the connection off
    (with a visible reason) instead of retrying forever.
"""
import re
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import SessionLocal
from app.services import calendar_encryption
from app.services import library as library_service

WEBHOOK_RE = re.compile(
    r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/(\d{5,25})/([A-Za-z0-9_\-]{20,120})$"
)

MAX_FAILURES = 5
NUDGE_WINDOW_HOURS = 3     # tolerate a late or skipped hourly run
USERNAME = "Riseply Coach"
COLOR = 0x2F8F6B


# ---------- webhook handling ----------

def parse_webhook(url: str) -> tuple[str, str] | None:
    m = WEBHOOK_RE.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def hint_for(url: str) -> str:
    parsed = parse_webhook(url)
    if not parsed:
        return ""
    wid, token = parsed
    return f"…/webhooks/{wid[:4]}…{wid[-2:]}/…{token[-4:]}"


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def _safe(text: str, limit: int) -> str:
    """Truncates and defuses mass-mention text. (allowed_mentions already
    blocks pings; this keeps the text from even looking like one.)"""
    text = (text or "").replace("@everyone", "@​everyone").replace("@here", "@​here")
    text = re.sub(r"<@[&!]?\d+>", "[mention]", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_payload(title: str, description: str, *, url: str | None = None, fields: list[tuple[str, str]] | None = None) -> dict:
    embed = {"title": _safe(title, 200), "description": _safe(description, 1800), "color": COLOR}
    if url:
        embed["url"] = url
    if fields:
        embed["fields"] = [{"name": _safe(n, 100), "value": _safe(v, 500), "inline": True} for n, v in fields[:6]]
    return {"username": USERNAME, "allowed_mentions": {"parse": []}, "embeds": [embed]}


def _post(webhook_url: str, payload: dict) -> tuple[bool, int | None, str]:
    """(ok, http_status, error). Never raises."""
    if not parse_webhook(webhook_url):
        return False, None, "Not a valid Discord webhook URL."
    try:
        r = requests.post(webhook_url, json=payload, timeout=6, allow_redirects=False)
    except requests.RequestException as e:
        return False, None, f"Couldn't reach Discord ({type(e).__name__})."
    if r.status_code in (200, 204):
        return True, r.status_code, ""
    return False, r.status_code, f"Discord returned HTTP {r.status_code}."


def get_url(conn: models.DiscordConnection) -> str:
    return calendar_encryption.decrypt_token(conn.webhook_url_enc)


def send(db: Session, conn: models.DiscordConnection, payload: dict) -> bool:
    """Sends one message and does the failure bookkeeping. 404/401/403 mean
    the webhook was deleted or revoked, so the connection is switched off
    right away; other failures count toward MAX_FAILURES; 429 (rate
    limited) is just skipped."""
    try:
        url = get_url(conn)
    except Exception as e:
        print(f"[discord] Couldn't decrypt webhook for user {conn.user_id}: {type(e).__name__}")
        return False
    ok, status, error = _post(url, payload)
    if ok:
        conn.consecutive_failures = 0
        conn.last_error = ""
        conn.last_success_at = datetime.utcnow()
    elif status in (401, 403, 404):
        conn.enabled = False
        conn.last_error = "Discord says this webhook no longer exists. Reconnect with a new webhook URL."
    elif status == 429:
        pass
    else:
        conn.consecutive_failures = (conn.consecutive_failures or 0) + 1
        conn.last_error = error
        if conn.consecutive_failures >= MAX_FAILURES:
            conn.enabled = False
            conn.last_error = "Turned off after repeated delivery failures. Reconnect to resume."
    db.commit()
    return ok


def _active_conn(db: Session, user_id: int, flag: str | None = None) -> models.DiscordConnection | None:
    conn = db.query(models.DiscordConnection).filter_by(user_id=user_id, enabled=True).first()
    if conn and flag and not getattr(conn, flag):
        return None
    return conn


# ---------- practice stats ----------

def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def practice_dates(db: Session, user_id: int, tz: ZoneInfo, now: datetime | None = None) -> set[date]:
    """Local calendar dates (in the user's timezone) on which they sent at
    least one message to the Career Coach, over the last ~13 months."""
    now = now or datetime.utcnow()
    since = now - timedelta(days=400)
    rows = db.query(models.CareerCoachMessage.created_at).filter(
        models.CareerCoachMessage.user_id == user_id,
        models.CareerCoachMessage.role == "user",
        models.CareerCoachMessage.created_at >= since,
    ).all()
    return {r[0].replace(tzinfo=dt_timezone.utc).astimezone(tz).date() for r in rows if r[0]}


def streak_days(dates: set[date], today: date) -> int:
    """Consecutive practice days ending today, or ending yesterday if they
    haven't practiced yet today (the streak is still alive until midnight)."""
    day = today if today in dates else today - timedelta(days=1)
    n = 0
    while day in dates:
        n += 1
        day -= timedelta(days=1)
    return n


def _latest_role(db: Session, user_id: int) -> str:
    row = db.query(models.CareerCoachSession.target_role).filter_by(user_id=user_id).order_by(
        models.CareerCoachSession.created_at.desc()).first()
    return row[0] if row else ""


def _coach_link() -> str:
    return settings.frontend_url.rstrip("/") + "/dashboard/career-coach"


# ---------- message builders ----------

def nudge_payload(streak: int, role: str, day_seed: int) -> dict:
    where = f" for {role}" if role else ""
    if streak >= 2:
        title = f"🔥 Your {streak}-day streak ends tonight"
        body = f"One short session{where} keeps it alive. Even five minutes counts."
    elif streak == 1:
        title = "Day 2 is where habits start"
        body = f"You practiced yesterday. A quick drill{where} today makes it a streak."
    else:
        options = [
            ("Ready for a quick rep?", f"A 5-minute drill{where} is enough to get moving again."),
            ("Small step, big momentum", f"Pick one thing{where} and practice it for a few minutes."),
            ("Your coach is ready when you are", f"Try a mock interview or a quick drill{where} today."),
        ]
        title, body = options[day_seed % len(options)]
    return build_payload(title, body, url=_coach_link(), fields=[("Open", "Career Coach")])


def recap_payload(sessions: int, avg_score: int | None, practice_days: int, streak: int, focus: str) -> dict:
    lines = [f"**{sessions}** session{'s' if sessions != 1 else ''} finished · **{practice_days}** day{'s' if practice_days != 1 else ''} practiced"]
    if avg_score is not None:
        lines.append(f"Average score: **{avg_score}/100**")
    if streak:
        lines.append(f"Current streak: **{streak}** day{'s' if streak != 1 else ''} 🔥")
    if focus:
        lines.append(f"Next focus: {focus}")
    lines.append("Same time next week? Even one session keeps the momentum going.")
    return build_payload("Your week in review", "\n".join(lines), url=_coach_link())


def followup_payload(session: models.CareerCoachSession, resource: models.LibraryItem | None, streak: int) -> dict:
    score = f"{session.score}/100" if session.score is not None else "not scored"
    desc = _safe(session.feedback or "Nice work finishing a session.", 600)
    fields = [("Score", score), ("Topic", session.topic or "Practice")]
    if streak >= 2:
        fields.append(("Streak", f"{streak} days 🔥"))
    if resource:
        desc += f"\n\n📚 **Go deeper:** [{_safe(resource.title, 100)}]({resource.url})"
    return build_payload(f"Session complete: {session.topic or 'Practice'}", desc, url=_coach_link(), fields=fields)


# ---------- triggers ----------

def send_session_followup(session_id: int) -> None:
    """Background task after a scored session. Opens its own DB session
    (the request's is closed by then) and swallows every error."""
    db = SessionLocal()
    try:
        session = db.query(models.CareerCoachSession).filter_by(id=session_id).first()
        if not session:
            return
        conn = _active_conn(db, session.user_id, "followup_enabled")
        if not conn:
            return
        tz = _tz(conn.timezone)
        streak = streak_days(practice_dates(db, session.user_id, tz), datetime.now(tz).date())
        items = db.query(models.LibraryItem).filter(models.LibraryItem.active.is_(True)).all()
        best = library_service.retrieve(items, f"{session.target_role} {session.topic}", limit=1)
        send(db, conn, followup_payload(session, best[0] if best else None, streak))
    except Exception as e:
        print(f"[discord] Session follow-up failed for session {session_id}: {type(e).__name__}: {e}")
    finally:
        db.close()


def notify_new_match(db: Session, user: models.User, job: dict) -> None:
    conn = _active_conn(db, user.id, "matches_enabled")
    if not conn:
        return
    title = job.get("title", "A new match")
    company = job.get("company", "")
    score = job.get("match_score")
    desc = f"**{title}**" + (f" at {company}" if company else "")
    if job.get("match_reason"):
        desc += f"\n{job['match_reason']}"
    fields = [("Match", f"{score}%")] if score is not None else []
    if job.get("location"):
        fields.append(("Location", job["location"]))
    send(db, conn, build_payload("New job match", desc, url=job.get("url") or None, fields=fields))


def notify_digest(db: Session, user: models.User, matches: list[dict]) -> None:
    conn = _active_conn(db, user.id, "matches_enabled")
    if not conn or not matches:
        return
    top = sorted(matches, key=lambda m: m.get("match_score") or 0, reverse=True)[:5]
    lines = [f"• **{m.get('title','')}** at {m.get('company','')} — {m.get('match_score','?')}%" for m in top]
    extra = f"\n…and {len(matches) - 5} more" if len(matches) > 5 else ""
    send(db, conn, build_payload(f"{len(matches)} new match{'es' if len(matches) != 1 else ''} today", "\n".join(lines) + extra,
                                 url=settings.frontend_url.rstrip("/") + "/dashboard"))


def _in_window(local_hour: int, target_hour: int) -> bool:
    return target_hour <= local_hour < target_hour + NUDGE_WINDOW_HOURS


def should_nudge(dates: set[date], today: date) -> bool:
    """Whether to send today's practice nudge to someone who hasn't
    practiced yet today. Backs off for people who've gone quiet so the
    bot never turns into nagging: after 14 idle days only every third
    day, and after 30 idle days not at all."""
    if today in dates:
        return False
    if not dates:
        return True
    idle = (today - max(dates)).days
    if idle > 30:
        return False
    if idle > 14:
        return idle % 3 == 0
    return True


def run_nudges(db: Session, now: datetime | None = None) -> dict:
    """Hourly job. For each enabled connection whose local time is inside
    its nudge window: send at most one practice nudge per local day, and
    on Sundays one weekly recap (which replaces that day's nudge)."""
    now_utc = (now or datetime.utcnow()).replace(tzinfo=dt_timezone.utc)
    sent_nudges = sent_recaps = skipped = 0

    rows = (
        db.query(models.DiscordConnection)
        .join(models.User, models.User.id == models.DiscordConnection.user_id)
        .filter(models.DiscordConnection.enabled.is_(True), models.User.is_suspended.is_(False))
        .all()
    )
    for conn in rows:
        try:
            tz = _tz(conn.timezone)
            local = now_utc.astimezone(tz)
            today = local.date()
            if not _in_window(local.hour, conn.nudge_hour if conn.nudge_hour is not None else 18):
                continue

            dates = practice_dates(db, conn.user_id, tz, now_utc.replace(tzinfo=None))
            streak = streak_days(dates, today)
            iso = local.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"

            recap_sent = False
            if conn.progress_enabled and local.weekday() == 6 and conn.last_recap_week != week_key:
                week_start = today - timedelta(days=6)
                week_days = {d for d in dates if week_start <= d <= today}
                since_utc = datetime.combine(week_start, datetime.min.time(), tzinfo=tz).astimezone(dt_timezone.utc).replace(tzinfo=None)
                done = db.query(models.CareerCoachSession).filter(
                    models.CareerCoachSession.user_id == conn.user_id,
                    models.CareerCoachSession.status == "completed",
                    models.CareerCoachSession.completed_at >= since_utc,
                ).all()
                conn.last_recap_week = week_key
                if week_days or done:
                    scores = [s.score for s in done if s.score is not None]
                    worst = min((s for s in done if s.score is not None), key=lambda s: s.score, default=None)
                    focus = f"revisit “{worst.topic}”" if worst and worst.score < 75 and worst.topic else ""
                    avg = round(sum(scores) / len(scores)) if scores else None
                    if send(db, conn, recap_payload(len(done), avg, len(week_days), streak, focus)):
                        sent_recaps += 1
                        recap_sent = True
                db.commit()

            if conn.nudge_enabled and conn.last_nudge_date != today:
                conn.last_nudge_date = today  # one decision per local day, sent or not
                db.commit()
                if recap_sent:
                    continue
                if should_nudge(dates, today):
                    if send(db, conn, nudge_payload(streak, _latest_role(db, conn.user_id), today.toordinal())):
                        sent_nudges += 1
                else:
                    skipped += 1
        except Exception as e:
            print(f"[discord] Nudge run failed for connection {conn.id}: {type(e).__name__}: {e}")
    return {"discord_nudges_sent": sent_nudges, "discord_recaps_sent": sent_recaps, "discord_skipped": skipped}
