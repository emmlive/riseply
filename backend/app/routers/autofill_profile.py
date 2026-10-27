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


# ---------- questions Autofill couldn't answer ----------

def _q_out(r: models.UnansweredQuestion) -> dict:
    return {"id": r.id, "question": r.question, "host": r.host or "", "times_seen": r.times_seen or 1,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None}


def _own_question(db: Session, qid: int, user_id: int) -> models.UnansweredQuestion:
    r = db.query(models.UnansweredQuestion).filter_by(id=qid, user_id=user_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Question not found.")
    return r


@router.get("/unanswered")
def list_unanswered(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = (db.query(models.UnansweredQuestion).filter_by(user_id=user.id, status="open")
            .order_by(models.UnansweredQuestion.last_seen.desc()).limit(50).all())
    return {"questions": [_q_out(r) for r in rows]}


@router.post("/unanswered/{qid}/answer")
def answer_unanswered(qid: int, body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Save the person's answer as a saved answer, so Autofill uses it next time."""
    r = _own_question(db, qid, user.id)
    answer = str(body.get("answer") or "").strip()[:2000]
    if not answer:
        raise HTTPException(status_code=422, detail="Write an answer first.")
    data = load(db, user.id)
    same = next((qa for qa in data["saved_answers"] if svc_key(qa["question"]) == svc_key(r.question)), None)
    if same:
        same["answer"] = answer
    elif len(data["saved_answers"]) >= 30:
        raise HTTPException(status_code=400, detail="You have 30 saved answers already. Remove one on the Autofill profile page first.")
    else:
        data["saved_answers"].append({"question": r.question[:200], "answer": answer})
    saved = _save(db, user.id, data)
    r.status = "answered"
    db.commit()
    return {"profile": saved}


@router.post("/unanswered/{qid}/dismiss", status_code=204)
def dismiss_unanswered(qid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    r = _own_question(db, qid, user.id)
    r.status = "dismissed"
    db.commit()


def svc_key(q: str) -> str:
    from app.services.unanswered import key_of
    return key_of(q or "")
