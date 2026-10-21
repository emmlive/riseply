import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import task_guide as task_guide_service
from app.services import usage

# "My manager gave me this and I don't know where to start." Saved guides, so
# reopening one is free. Building one counts as a task_guide; each question or
# piece of work sent for review counts as a coaching message.
router = APIRouter(prefix="/task-guides", tags=["task-guides"])

BUILD_ACTION = "task_guide"
HELP_ACTION = "coaching_message"


def _get(db: Session, user_id: int, guide_id: int) -> models.TaskGuide:
    row = db.query(models.TaskGuide).filter_by(id=guide_id, user_id=user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Guide not found")
    return row


def _done(row: models.TaskGuide) -> list[str]:
    try:
        v = json.loads(row.done or "[]")
        return [str(i) for i in v] if isinstance(v, list) else []
    except Exception:
        return []


def _out(row: models.TaskGuide) -> schemas.TaskGuideOut:
    data = json.loads(row.data or "{}")
    data.pop("title", None)
    return schemas.TaskGuideOut(
        id=row.id, title=row.title, task_text=row.task_text, role=row.role, level=row.level,
        created_at=row.created_at, done=_done(row), **data,
    )


@router.get("", response_model=list[schemas.TaskGuideListItem])
def list_guides(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.TaskGuide).filter_by(user_id=user.id).order_by(models.TaskGuide.id.desc()).limit(30).all()
    out = []
    for r in rows:
        try:
            steps = json.loads(r.data or "{}").get("steps", [])
        except Exception:
            steps = []
        ids = {s.get("id") for s in steps if isinstance(s, dict)}
        out.append(schemas.TaskGuideListItem(
            id=r.id, title=r.title or "Task", created_at=r.created_at,
            steps=len(steps), done=len([d for d in _done(r) if d in ids]),
        ))
    return out


@router.get("/{guide_id}", response_model=schemas.TaskGuideOut)
def get_guide(guide_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _out(_get(db, user.id, guide_id))


@router.post("", response_model=schemas.TaskGuideOut)
def build(payload: schemas.TaskGuideRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    usage.check_and_increment(db, user, BUILD_ACTION, 1)
    try:
        data = task_guide_service.build(payload.task.strip(), payload.role.strip(), payload.level, user.resume_text or "")
    except Exception as e:
        usage.decrement(db, user.id, BUILD_ACTION, 1)
        print(f"[task_guide] build failed for user {user.id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Couldn't build the guide right now, and this attempt wasn't counted against your limit. Try again shortly.",
        )
    row = models.TaskGuide(
        user_id=user.id, title=data["title"], task_text=payload.task.strip(), role=payload.role.strip(),
        level=payload.level, data=json.dumps(data), done="[]",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.put("/{guide_id}/progress", response_model=schemas.TaskGuideOut)
def save_progress(guide_id: int, payload: schemas.TaskGuideProgress, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    valid = {s["id"] for s in json.loads(row.data or "{}").get("steps", [])}
    row.done = json.dumps([d for d in dict.fromkeys(payload.done) if d in valid])
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{guide_id}/help", response_model=schemas.TaskGuideHelpOut)
def help_with_step(guide_id: int, payload: schemas.TaskGuideHelpRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    usage.check_and_increment(db, user, HELP_ACTION, 1)
    try:
        reply = task_guide_service.help_reply(
            row.task_text, json.loads(row.data or "{}"), payload.step_id, payload.message,
            [t.model_dump() for t in payload.history], row.level,
        )
    except Exception as e:
        usage.decrement(db, user.id, HELP_ACTION, 1)
        print(f"[task_guide] help failed for guide {guide_id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't get an answer right now, and this wasn't counted against your limit. Try again shortly.")
    return schemas.TaskGuideHelpOut(reply=reply)


@router.delete("/{guide_id}")
def delete_guide(guide_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    db.delete(row)
    db.commit()
    return {"ok": True}
