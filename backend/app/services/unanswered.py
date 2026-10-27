"""Questions Autofill couldn't answer: record them, let the person answer them
once, and count them across people so the product knows what to support next.

Only the question text is kept, and text that looks like personal data (an
email address, a phone or ID number) is dropped before anything is stored."""
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app import models

MAX_PER_CALL = 40
MIN_LEN, MAX_LEN = 8, 300


def clean_question(q) -> str:
    q = re.sub(r"[\x00-\x1f\x7f]", " ", str(q or ""))
    return re.sub(r"\s+", " ", q).strip()[:MAX_LEN]


def key_of(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()[:200]


def usable(q: str) -> bool:
    if not (MIN_LEN <= len(q) <= MAX_LEN):
        return False
    if "@" in q or re.search(r"\d(?:[\s().+-]*\d){6,}", q):  # email, phone or ID number
        return False
    if re.search(r"https?://", q, re.I):
        return False
    return len(key_of(q)) >= MIN_LEN


def record(db: Session, user_id: int, questions, host: str = "") -> int:
    """Remember these questions for this person. Returns how many were new."""
    host = re.sub(r"[^a-z0-9.\-]", "", str(host or "").lower())[:100]
    seen, new = set(), 0
    for raw in list(questions or [])[:MAX_PER_CALL]:
        q = clean_question(raw)
        k = key_of(q)
        if not usable(q) or k in seen:
            continue
        seen.add(k)
        row = db.query(models.UnansweredQuestion).filter_by(user_id=user_id, qkey=k).first()
        if row is None:
            db.add(models.UnansweredQuestion(user_id=user_id, question=q, qkey=k, host=host))
            new += 1
        else:
            row.times_seen = (row.times_seen or 0) + 1
            row.last_seen = datetime.utcnow()
            if host:
                row.host = host
            if row.status == "answered":
                # They answered it but the form still wasn't filled: show it again.
                row.status = "open"
    db.commit()
    return new
