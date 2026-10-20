"""Learning from the person's own decisions about matches.

When someone rejects a match they can say why (a fixed set of reasons, plus
an optional short note). The recent rejections-with-reasons, and the matches
they approved, are summarised into a short block that is shown to the scoring
model as a soft signal. No extra AI call, so no extra cost: the matcher just
sees what the person has already told us.

The reasons are a fixed list, so they can only say things about the job
(level, pay, place, field, company, tools). Free-text notes are clipped and
passed as data, never as instructions.
"""
import re

from sqlalchemy.orm import Session

from app import models

REASONS = {
    "level_too_junior": "the level was too junior",
    "level_too_senior": "the level was too senior",
    "pay": "the pay looked too low",
    "location": "the location or commute didn't work",
    "field": "it was the wrong field or kind of work",
    "company": "they don't want to work for that company",
    "tools": "the tools or skills weren't what they want to use",
    "not_interested": "the role just didn't interest them",
}
MIN_SIGNALS = 2  # fewer reasoned rejections than this is too thin to act on


def clean_note(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:140]


def notes_for(db: Session, user_id: int) -> str:
    """The summary block for the scoring prompt, or "" when there isn't
    enough yet."""
    rejected = (
        db.query(models.Application, models.Job)
        .join(models.Job, models.Job.id == models.Application.job_id)
        .filter(models.Application.user_id == user_id, models.Application.status == "rejected",
                models.Application.reject_reason != "")
        .order_by(models.Application.status_updated_at.desc()).limit(12).all()
    )
    if len(rejected) < MIN_SIGNALS:
        return ""
    lines = ["Passed on:"]
    for a, j in rejected:
        why = REASONS.get(a.reject_reason, "")
        if not why:
            continue
        note = clean_note(a.reject_note)
        lines.append(f"- {clean_note(j.title)[:80]} at {clean_note(j.company)[:60]}: {why}" + (f" (\"{note}\")" if note else ""))
    liked = (
        db.query(models.Job)
        .join(models.Application, models.Job.id == models.Application.job_id)
        .filter(models.Application.user_id == user_id,
                models.Application.status.in_(["approved", "submitted", "interviewing", "accepted"]))
        .order_by(models.Application.status_updated_at.desc()).limit(6).all()
    )
    if liked:
        lines.append("Wanted:")
        lines += [f"- {clean_note(j.title)[:80]} at {clean_note(j.company)[:60]}" for j in liked]
    return "\n".join(lines) if len(lines) > 1 else ""
