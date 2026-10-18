import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import fit_score as fit_score_service
from app.services import resume_customizer, usage

# "How much did tailoring help?" -- the person's original resume and the
# tailored one scored against the same job. Computed once per application and
# saved; re-running is explicit and metered like any other AI call.
router = APIRouter(prefix="/applications", tags=["fit-score"])

ACTION = "fit_score"


@router.post("/{application_id}/fit-score", response_model=schemas.FitScoreOut)
def fit_score(
    application_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    if not app_row.tailored_resume_data:
        raise HTTPException(status_code=404, detail="Tailor your resume for this job first, then compare it.")

    if app_row.fit_score_data and not refresh:
        try:
            return schemas.FitScoreOut(**json.loads(app_row.fit_score_data), cached=True)
        except Exception:
            pass  # unreadable saved copy: fall through and recompute

    if not (user.resume_text or "").strip():
        raise HTTPException(status_code=400, detail="Add your resume first -- the score compares it with the tailored version.")

    try:
        tailored = resume_customizer._all_text(resume_customizer.docx_to_blocks(app_row.tailored_resume_data))
    except Exception:
        raise HTTPException(status_code=422, detail="This tailored resume couldn't be read, so it can't be scored.")
    job = db.get(models.Job, app_row.job_id)
    job_dict = {"title": job.title, "company": job.company, "description": job.description}

    usage.check_and_increment(db, user, ACTION, 1)
    try:
        result = fit_score_service.score(user.resume_text, tailored, job_dict)
    except Exception:
        usage.decrement(db, user.id, ACTION, 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't score your resume right now -- this attempt wasn't counted against your limit. Try again shortly.",
        )

    app_row.fit_score_data = json.dumps(result)
    db.commit()
    return schemas.FitScoreOut(**result)
