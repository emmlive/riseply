import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import career_path as career_path_service
from app.services import usage

# "How do I get from here to that role?" -- a staged plan built from the
# person's resume. Saved, so reopening the page is free; asking for the same
# role, time and resume again returns the saved plan unless they ask to redo.
router = APIRouter(prefix="/career-path", tags=["career-path"])

ACTION = "career_path"


def _out(row: models.CareerPathPlan, cached: bool = False) -> schemas.CareerPathOut:
    data = json.loads(row.data or "{}")
    return schemas.CareerPathOut(
        id=row.id, target_role=row.target_role, months=row.months, hours_per_week=row.hours_per_week,
        created_at=row.created_at, cached=cached, **data,
    )


@router.get("/latest", response_model=schemas.CareerPathOut | None)
def latest(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.query(models.CareerPathPlan).filter_by(user_id=user.id).order_by(models.CareerPathPlan.id.desc()).first()
    if not row:
        return None
    try:
        return _out(row)
    except Exception:
        return None  # unreadable saved plan: show the empty form


@router.post("", response_model=schemas.CareerPathOut)
def build(payload: schemas.CareerPathRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    role = payload.target_role.strip()
    if not (user.resume_text or "").strip():
        raise HTTPException(status_code=400, detail="Add your resume first -- the plan starts from where it says you are.")

    rhash = career_path_service.resume_hash(user.resume_text)
    if not payload.refresh:
        same = db.query(models.CareerPathPlan).filter_by(
            user_id=user.id, resume_hash=rhash, months=payload.months, hours_per_week=payload.hours_per_week,
        ).order_by(models.CareerPathPlan.id.desc()).first()
        if same and same.target_role.lower() == role.lower():
            try:
                return _out(same, cached=True)
            except Exception:
                pass  # unreadable saved plan: write a new one

    usage.check_and_increment(db, user, ACTION, 1)
    try:
        result = career_path_service.plan(role, user.resume_text, payload.months, payload.hours_per_week)
    except Exception:
        usage.decrement(db, user.id, ACTION, 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't build your plan right now -- this attempt wasn't counted against your limit. Try again shortly.",
        )

    row = models.CareerPathPlan(
        user_id=user.id, target_role=role, resume_hash=rhash,
        months=payload.months, hours_per_week=payload.hours_per_week, data=json.dumps(result),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)
