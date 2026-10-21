"""Experience the person adds so a tailored resume can show it truthfully.

A tailored resume can only reorder and reword what the base resume says, so a
skill the person really has but never wrote down stays invisible to the screen.
Here they state it in their own words ("Python: built the monthly controls
dashboard") and tailoring may use it. They are the source of every fact, and
the page tells them to add only what they can talk about in an interview.
"""
import re

from sqlalchemy.orm import Session

from app import models

MAX_FACTS = 25


def _clip(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def add(db: Session, user_id: int, skill: str, detail: str) -> models.ResumeFact | None:
    skill, detail = _clip(skill, 60), _clip(detail, 240)
    if len(skill) < 2 or len(detail) < 8:
        return None
    existing = db.query(models.ResumeFact).filter_by(user_id=user_id).all()
    for f in existing:
        if f.skill.lower() == skill.lower():
            f.detail = detail
            db.commit()
            return f
    if len(existing) >= MAX_FACTS:
        return None
    row = models.ResumeFact(user_id=user_id, skill=skill, detail=detail)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def for_prompt(db: Session, user_id: int) -> list[dict]:
    rows = db.query(models.ResumeFact).filter_by(user_id=user_id).order_by(models.ResumeFact.id).limit(MAX_FACTS).all()
    return [{"skill": r.skill, "detail": r.detail} for r in rows]
