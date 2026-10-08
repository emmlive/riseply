"""Progress: what the person has actually done and how it's going.

Read-only. Everything here is computed from rows that already exist
(coach sessions and their scores, applications, study notes), so there is
nothing new to store and nothing to keep in sync. The one judgment call is
honesty about thin data: a "change" is only reported once there are enough
scored sessions to compare, and a rate only once there are enough
applications for it to mean something.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models

WEEKS = 8
MAX_SCORE_POINTS = 40
MIN_APPS_FOR_RATE = 5
# Statuses that mean "past the review step" / "an application went out" etc.
_NOT_APPROVED = ("pending_approval", "rejected")
_APPLIED = ("submitted", "interviewing", "offer")
_INTERVIEW = ("interviewing", "offer")


def _local(dt: datetime, tz_offset: int) -> datetime:
    # tz_offset is JavaScript's getTimezoneOffset(): minutes the local time is
    # BEHIND UTC (Chicago in October is 300), so local = utc - offset.
    return dt - timedelta(minutes=tz_offset)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _avg(values: list[int]) -> float:
    return sum(values) / len(values)


def recent_change(scores: list[int]) -> int | None:
    """Average of the latest few scores minus the few before them. Needs two
    scored sessions; with 2-3 it is simply latest vs the one before."""
    n = len(scores)
    if n < 2:
        return None
    k = min(3, n // 2)
    return round(_avg(scores[-k:]) - _avg(scores[-2 * k:-k]))


# --- Readiness -------------------------------------------------------------
# Two questions the person cares about, answered per target role from the
# coach's own scores: "Am I ready to GET this job?" (mock interviews and
# resume coaching) and "Am I ready to DO this job?" (task walkthroughs and
# knowledge drills). It is the coach's assessment of practice, not a
# prediction of a hiring outcome, and the page says so.
GET_JOB = (("interview", 0.6), ("resume", 0.4))
DO_JOB = (("walkthrough", 0.6), ("drill", 0.4))
RECENT = 3          # each session type counts its latest few scores
EARLY_UNDER = 3     # fewer scored sessions than this is an "early read"
# (minimum score, level). Checked top to bottom.
LEVELS = ((80, "ready"), (65, "close"), (50, "building"), (0, "starting"))
NEXT_ORDER = ("interview", "walkthrough", "drill", "resume")   # what to try first if untouched
NEXT_NAMES = {"interview": "a mock interview", "walkthrough": "a task walkthrough",
              "drill": "a knowledge drill", "resume": "resume coaching"}


def level_for(score: int | None) -> str:
    if score is None:
        return "none"
    return next(name for floor, name in LEVELS if score >= floor)


def _dimension(by_type: dict[str, list[int]], weights: tuple) -> dict:
    parts, num, den, total = [], 0.0, 0.0, 0
    for stype, weight in weights:
        vals = by_type.get(stype, [])
        score = round(_avg(vals[-RECENT:])) if vals else None
        parts.append({"session_type": stype, "sessions": len(vals), "score": score})
        total += len(vals)
        if score is not None:
            num += weight * score
            den += weight
    score = round(num / den) if den else None   # a missing part doesn't count as zero
    early = total < EARLY_UNDER
    level = level_for(score)
    if early and level == "ready":
        level = "close"   # "Ready" needs enough sessions behind it; one good score is a promising start
    return {"score": score, "level": level, "sessions": total, "early": early, "parts": parts}


def readiness_from_sessions(sessions: list) -> list[dict]:
    """sessions: CareerCoachSession rows (any status). Only scored, completed
    sessions count. Roles are grouped ignoring case and spacing."""
    scored = [s for s in sessions if s.status == "completed" and s.score is not None]
    scored.sort(key=lambda s: (s.completed_at or s.created_at, s.id))
    roles: dict[str, dict] = {}
    for s in scored:
        key = s.target_role.strip().lower()
        r = roles.setdefault(key, {"name": s.target_role.strip(), "by_type": defaultdict(list), "n": 0, "last": None})
        r["by_type"][s.session_type].append(s.score)
        r["n"] += 1
        r["last"] = s.completed_at or s.created_at
    out = []
    for r in sorted(roles.values(), key=lambda r: r["last"], reverse=True)[:6]:
        by_type = r["by_type"]
        untouched = [t for t in NEXT_ORDER if not by_type.get(t)]
        if untouched:
            nxt, reason = untouched[0], f"You haven't tried {NEXT_NAMES[untouched[0]]} for this role yet."
        else:
            nxt = min(NEXT_ORDER, key=lambda t: (_avg(by_type[t][-RECENT:]), NEXT_ORDER.index(t)))
            reason = f"{NEXT_NAMES[nxt].capitalize()} is your lowest area right now."
        out.append({
            "target_role": r["name"], "scored_sessions": r["n"],
            "get_job": _dimension(by_type, GET_JOB), "do_job": _dimension(by_type, DO_JOB),
            "next_type": nxt, "next_reason": reason,
        })
    return out


def build_readiness(db: Session, user: models.User) -> list[dict]:
    rows = db.query(models.CareerCoachSession).filter(models.CareerCoachSession.user_id == user.id).all()
    return readiness_from_sessions(rows)


def build_progress(db: Session, user: models.User, tz_offset: int = 0, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    today = _local(now, tz_offset).date()

    # --- Practice (Career Coach) ---
    sessions = (
        db.query(models.CareerCoachSession)
        .filter(models.CareerCoachSession.user_id == user.id)
        .order_by(models.CareerCoachSession.created_at.asc(), models.CareerCoachSession.id.asc())
        .all()
    )
    completed = [s for s in sessions if s.status == "completed"]
    scored = [s for s in completed if s.score is not None]
    # Order by when the session finished, so the trend reads in time order.
    scored.sort(key=lambda s: (s.completed_at or s.created_at, s.id))
    score_values = [s.score for s in scored]

    points = [
        {
            "session_id": s.id, "date": s.completed_at or s.created_at,
            "target_role": s.target_role, "session_type": s.session_type,
            "topic": s.topic or "", "score": s.score,
        }
        for s in scored[-MAX_SCORE_POINTS:]
    ]

    roles: dict[str, list] = defaultdict(list)
    role_sessions: dict[str, int] = defaultdict(int)
    for s in completed:
        role_sessions[s.target_role.strip().lower()] += 1
    names: dict[str, str] = {}
    for s in scored:
        key = s.target_role.strip().lower()
        names.setdefault(key, s.target_role.strip())
        roles[key].append(s.score)
    for s in completed:
        names.setdefault(s.target_role.strip().lower(), s.target_role.strip())
    by_role = []
    for key, count in role_sessions.items():
        vals = roles.get(key, [])
        by_role.append({
            "target_role": names[key], "sessions": count, "scored": len(vals),
            "first_score": vals[0] if vals else None,
            "latest_score": vals[-1] if vals else None,
            "change": (vals[-1] - vals[0]) if len(vals) >= 2 else None,
        })
    by_role.sort(key=lambda r: (-r["sessions"], r["target_role"]))

    topics: dict[str, list[int]] = defaultdict(list)
    topic_names: dict[str, str] = {}
    for s in scored:
        t = (s.topic or "").strip()
        if not t:
            continue
        topics[t.lower()].append(s.score)
        topic_names.setdefault(t.lower(), t)
    weakest = sorted(
        ({"topic": topic_names[k], "sessions": len(v), "avg_score": round(_avg(v), 1)} for k, v in topics.items()),
        key=lambda t: (t["avg_score"], t["topic"]),
    )[:3]

    notes_saved = db.query(func.count(models.StudyNote.id)).filter(models.StudyNote.user_id == user.id).scalar() or 0
    folders = db.query(func.count(models.StudyFolder.id)).filter(models.StudyFolder.user_id == user.id).scalar() or 0

    practice = {
        "sessions_completed": len(completed),
        "sessions_in_progress": len(sessions) - len(completed),
        "scored_sessions": len(scored),
        "avg_score": round(_avg(score_values), 1) if score_values else None,
        "best_score": max(score_values) if score_values else None,
        "latest_score": score_values[-1] if score_values else None,
        "change": recent_change(score_values),
        "scores": points,
        "by_role": by_role[:8],
        "weakest_topics": weakest,
        "notes_saved": notes_saved,
        "folders": folders,
    }

    # --- Job search (applications) ---
    apps = (
        db.query(
            models.Application.status, models.Application.created_at, models.Application.submitted_at,
        )
        .filter(models.Application.user_id == user.id)
        .all()
    )
    matched = len(apps)
    applied_n = sum(1 for a in apps if a.status in _APPLIED or a.submitted_at is not None)
    funnel = {
        "matched": matched,
        "approved": sum(1 for a in apps if (a.status or "pending_approval") not in _NOT_APPROVED),
        "applied": applied_n,
        "interviewing": sum(1 for a in apps if a.status in _INTERVIEW),
        "offers": sum(1 for a in apps if a.status == "offer"),
    }

    first_week = _monday(today) - timedelta(weeks=WEEKS - 1)
    weeks = {first_week + timedelta(weeks=i): {"matches": 0, "applied": 0, "practice": 0} for i in range(WEEKS)}

    def bump(dt: datetime | None, field: str):
        if not dt:
            return
        wk = _monday(_local(dt, tz_offset).date())
        if wk in weeks:
            weeks[wk][field] += 1

    for a in apps:
        bump(a.created_at, "matches")
        bump(a.submitted_at, "applied")
    for s in completed:
        bump(s.completed_at or s.created_at, "practice")

    return {
        "readiness": readiness_from_sessions(sessions),
        "practice": practice,
        "job_search": {
            "funnel": funnel,
            "interview_rate": round(100 * funnel["interviewing"] / funnel["applied"]) if funnel["applied"] >= MIN_APPS_FOR_RATE else None,
            "weeks": [{"week_start": k, **v} for k, v in sorted(weeks.items())],
        },
        "current_streak": user.current_streak or 0,
        "longest_streak": user.longest_streak or 0,
        "rise_points": user.rise_points or 0,
    }
