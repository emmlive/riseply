import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import skill_gap as skill_gap_service
from app.services import usage

# "What am I missing for the role I want?" -- the person's resume against a
# target role and the real listings Riseply has found for it, with a practice
# starting point for each gap. Metered (one analysis = one unit); a repeat of
# the same role and resume within a week is served from the saved report free.
router = APIRouter(prefix="/skill-gap", tags=["skill-gap"])

ACTION = "skill_gap"


def _out(row: models.SkillGapReport, cached: bool = False) -> schemas.SkillGapOut:
    data = json.loads(row.data or "{}")
    return schemas.SkillGapOut(id=row.id, target_role=row.target_role, created_at=row.created_at, cached=cached, **data)


@router.get("/suggestions", response_model=list[str])
def role_suggestions(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Roles the person already targets (from their search profiles), to
    save typing."""
    out: list[str] = []
    for p in db.query(models.SearchProfile).filter_by(user_id=user.id).all():
        for t in [p.name] + json.loads(p.titles or "[]"):
            t = (t or "").strip()
            if t and t.lower() not in {x.lower() for x in out}:
                out.append(t)
    return out[:8]


@router.get("/latest", response_model=list[schemas.SkillGapOut])
def latest(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.SkillGapReport).filter_by(user_id=user.id).order_by(models.SkillGapReport.id.desc()).limit(10).all()
    return [_out(r) for r in rows if skill_gap_service.is_current(r)][:5]


@router.post("", response_model=schemas.SkillGapOut)
def run(payload: schemas.SkillGapRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    role = payload.target_role.strip()
    if not (user.resume_text or "").strip():
        raise HTTPException(status_code=400, detail="Add your resume first -- the analysis compares it to the role.")

    rhash = skill_gap_service.resume_hash(user.resume_text)
    cached = skill_gap_service.find_cached(db, user.id, role, rhash)
    current = bool(cached) and skill_gap_service.is_current(cached)
    if current and not payload.refresh:
        return _out(cached, cached=True)

    # A saved report from before the text-length fix is stale: redoing it is
    # free, since the earlier one was cut short through no fault of the person.
    redo_of_stale = bool(cached) and not current
    if not redo_of_stale:
        usage.check_and_increment(db, user, ACTION, 1)
    jobs = skill_gap_service.gather_jobs(db, user, role)
    try:
        report = skill_gap_service.analyze(role, user.resume_text, jobs)
    except Exception:
        if not redo_of_stale:
            usage.decrement(db, user.id, ACTION, 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't analyze your skills right now -- this attempt wasn't counted against your limit. Try again shortly.",
        )

    row = models.SkillGapReport(
        user_id=user.id, target_role=role, resume_hash=rhash,
        jobs_used=report["jobs_used"], data=json.dumps(report),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)
