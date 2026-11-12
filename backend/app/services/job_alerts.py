"""Smart job alerts. People differ in how much email they want, so the person
chooses and the rest is worked out:

- A standout match (at or above their "instant" score) emails right away.
- Everything else that clears their floor waits for ONE digest, sent at the
  hour they picked in their own time zone, ranked best first and capped.
- If a digest has nothing, no email goes out. After a quiet week one short
  note says so and suggests what to widen, worked out from their own search.

All of the choosing is plain code here, so it can be tested without any email."""
import html
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings

DIGEST_GAP = timedelta(hours=20)     # at most one digest a day, whatever the schedule does
QUIET_EVERY = timedelta(days=7)      # a "nothing new" note at most weekly
MAX_SHOWN = 8
INSTANT_PER_DAY = 3                  # more than this and the rest join the digest
STRETCH_BELOW = 65


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def local_hour(user, now_utc: datetime) -> int:
    name = (getattr(user, "alert_timezone", "") or "").strip()
    tz = ZoneInfo(name) if name and valid_timezone(name) else ZoneInfo("America/Chicago")
    return now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).hour


def is_due(user, now_utc: datetime) -> bool:
    """True in the hour the person chose, once a day."""
    hour = 8 if user.alert_digest_hour is None else user.alert_digest_hour
    if local_hour(user, now_utc) != hour:
        return False
    last = user.last_digest_sent_at
    return last is None or now_utc - last >= DIGEST_GAP


def is_instant(score: int, user, sent_today: int) -> bool:
    """A standout match goes out now, up to a few a day."""
    return score >= (user.alert_instant_min_score or 85) and score >= (user.notification_min_score or 0) and sent_today < INSTANT_PER_DAY


def _money(m: dict) -> str:
    from app.services.notifier import _format_salary
    return _format_salary(m)


def _age(m: dict, now: datetime) -> str:
    posted = m.get("posted_at")
    if not posted:
        return ""
    days = (now - posted).days
    return "posted today" if days <= 0 else "posted yesterday" if days == 1 else f"posted {days} days ago" if days < 30 else ""


def choose(matches: list[dict], instant_min: int) -> dict:
    """Best first. 'best' are standout fits, 'good' the rest of what cleared the
    floor, and anything under STRETCH_BELOW is flagged as a stretch."""
    ranked = sorted(matches, key=lambda m: (-m["match_score"], str(m.get("title"))))
    shown, extra = ranked[:MAX_SHOWN], max(0, len(ranked) - MAX_SHOWN)
    return {
        "best": [m for m in shown if m["match_score"] >= instant_min],
        "good": [m for m in shown if m["match_score"] < instant_min],
        "extra": extra, "total": len(ranked),
    }


def subject_for(chosen: dict) -> str:
    n = chosen["total"]
    if chosen["best"]:
        top = chosen["best"][0]
        return f"{top['title']} at {top['company']} ({top['match_score']}%) and {n - 1} more" if n > 1 else f"{top['title']} at {top['company']} ({top['match_score']}%)"
    return f"{n} new job match{'es' if n != 1 else ''} for you"


def _dashboard() -> str:
    return f"{settings.frontend_url.rstrip('/')}/dashboard/applications"


def digest_text(chosen: dict, now: datetime) -> str:
    def block(m):
        bits = [f"{m['title']} at {m['company']} ({m['match_score']}%)", m.get("location") or ""]
        line2 = " | ".join(x for x in [_money(m), _age(m, now)] if x)
        why = m.get("match_reason") or ""
        stretch = "Stretch role: apply only if you can show the missing skills.\n" if m["match_score"] < STRETCH_BELOW else ""
        return "\n".join(x for x in [bits[0], bits[1], line2, why, stretch.strip(), m.get("url") or ""] if x)
    out = [f"{chosen['total']} new match{'es' if chosen['total'] != 1 else ''} since your last email.\n"]
    if chosen["best"]:
        out += ["STRONGEST FITS", *[block(m) + "\n" for m in chosen["best"]]]
    if chosen["good"]:
        out += ["ALSO WORTH A LOOK", *[block(m) + "\n" for m in chosen["good"]]]
    if chosen["extra"]:
        out.append(f"{chosen['extra']} more are waiting in your dashboard.")
    out.append(f"Review and approve them: {_dashboard()}\nChange how often you hear from us: {settings.frontend_url.rstrip('/')}/dashboard/profile")
    return "\n".join(out)


def digest_html(chosen: dict, now: datetime) -> str:
    e = html.escape

    def card(m):
        meta = " &middot; ".join(e(x) for x in [m.get("location") or "", _money(m), _age(m, now)] if x)
        stretch = '<div style="color:#8a5a00;font-size:13px;margin-top:6px">Stretch role. Apply only if you can show the missing skills.</div>' if m["match_score"] < STRETCH_BELOW else ""
        why = f'<div style="color:#3d4659;font-size:14px;margin-top:6px">{e(m["match_reason"])}</div>' if m.get("match_reason") else ""
        link = f'<a href="{e(m["url"])}" style="color:#1F7A6C;font-size:13px">View the posting</a>' if m.get("url") else ""
        return (f'<div style="border:1px solid #e2e5ea;border-radius:8px;padding:14px 16px;margin:0 0 10px">'
                f'<div style="font-weight:600;font-size:16px;color:#16233d">{e(m["title"])}</div>'
                f'<div style="color:#3d4659;font-size:14px">{e(m["company"])} &middot; <strong>{m["match_score"]}% match</strong></div>'
                f'<div style="color:#5b6478;font-size:13px;margin-top:2px">{meta}</div>{why}{stretch}<div style="margin-top:8px">{link}</div></div>')

    def section(title, rows):
        return f'<h3 style="font-size:14px;color:#17665a;margin:18px 0 8px">{e(title)}</h3>' + "".join(card(m) for m in rows) if rows else ""

    more = f'<p style="color:#5b6478;font-size:14px">{chosen["extra"]} more are waiting in your dashboard.</p>' if chosen["extra"] else ""
    return (f'<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;color:#16233d">'
            f'<p style="font-size:15px">{chosen["total"]} new match{"es" if chosen["total"] != 1 else ""} since your last email.</p>'
            + section("Strongest fits", chosen["best"]) + section("Also worth a look", chosen["good"]) + more +
            f'<p style="margin-top:18px"><a href="{e(_dashboard())}" style="background:#1F7A6C;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-size:14px">Review your matches</a></p>'
            f'<p style="color:#8a92a3;font-size:12px;margin-top:22px"><a href="{e(settings.frontend_url.rstrip("/"))}/dashboard/profile" style="color:#8a92a3">Change how often you hear from us</a></p></div>')


def widen_suggestion(profiles: list[dict]) -> str:
    """What to loosen, from the person's own search. Empty when nothing stands out."""
    active = [p for p in profiles if p.get("active", True)]
    if not active:
        return "You have no active search. Turn one on or add a job title to start getting matches."
    tips = []
    if any((p.get("min_match_score") or 0) >= 75 for p in active):
        tips.append("lower the minimum match score to about 65 so close roles show up")
    if not any(any(x.lower() in ("remote", "anywhere") for x in p.get("locations", [])) for p in active):
        tips.append("add Remote as a location")
    if sum(len(p.get("titles", [])) for p in active) < 3:
        tips.append("add two or three related job titles")
    return ("To widen it, " + "; ".join(tips) + ".") if tips else ""


def quiet_text(suggestion: str) -> str:
    return ("Nothing new matched your search this week. We are still checking every day, and you will hear from us as soon as something fits.\n\n"
            + (suggestion + "\n\n" if suggestion else "") + f"Your search settings: {settings.frontend_url.rstrip('/')}/dashboard/search-profiles")


def profiles_of(rows) -> list[dict]:
    out = []
    for r in rows:
        def load(v):
            try:
                return json.loads(v or "[]")
            except (ValueError, TypeError):
                return []
        out.append({"active": r.active, "min_match_score": r.min_match_score, "locations": load(r.locations), "titles": load(r.titles)})
    return out
