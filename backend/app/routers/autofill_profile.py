import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.security import get_current_user
from app.services import autofill_profile as svc, usage

# The details the browser extension fills on application forms: work history,
# education, standard answers and saved answers. Reading the resume to propose
# work history/education/skills is metered; everything else is plain storage.
router = APIRouter(prefix="/autofill-profile", tags=["autofill-profile"])

ACTION = "autofill_profile"


def _row(db: Session, user_id: int) -> models.AutofillProfile | None:
    return db.query(models.AutofillProfile).filter_by(user_id=user_id).first()


def load(db: Session, user_id: int) -> dict:
    r = _row(db, user_id)
    try:
        return svc.clean(json.loads(r.data)) if r else svc.empty()
    except Exception:
        return svc.empty()


def _save(db: Session, user_id: int, data: dict) -> dict:
    data = svc.clean(data)
    r = _row(db, user_id)
    if not r:
        r = models.AutofillProfile(user_id=user_id)
        db.add(r)
    r.data = json.dumps(data)
    r.updated_at = datetime.utcnow()
    db.commit()
    return data


@router.get("")
def get_profile(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return {"profile": load(db, user.id), "has_resume": bool((user.resume_text or "").strip())}


@router.put("")
def put_profile(body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return {"profile": _save(db, user.id, body.get("profile", body))}


@router.post("/from-resume")
def from_resume(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Propose work history, education and skills from the default resume.
    Replaces those three sections only; answers and saved answers are kept."""
    if not (user.resume_text or "").strip():
        raise HTTPException(status_code=400, detail="Add your resume in Riseply first, then I can read it.")
    usage.check_and_increment(db, user, ACTION)
    try:
        got = svc.extract(user.resume_text)
    except Exception as e:
        usage.decrement(db, user.id, ACTION, 1)
        print(f"[autofill-profile] extraction failed for user {user.id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't read your resume just now. Your allowance wasn't used. Try again.")
    cur = load(db, user.id)
    cur.update(got)
    return {"profile": _save(db, user.id, cur)}
