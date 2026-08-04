from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import interview_prep as interview_prep_service
from app.services import usage, rise_index

router = APIRouter(prefix="/applications", tags=["interview-prep"])


def _get_owned_application(db: Session, application_id: int, user_id: int) -> models.Application:
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user_id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_row


@router.post("/{application_id}/interview-prep", response_model=schemas.InterviewPrepOut)
def generate_interview_prep(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)

    existing = db.query(models.InterviewPrep).filter_by(application_id=application_id).first()
    if existing:
        return existing

    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume before generating interview prep.")

    usage.check_and_increment(db, user, "interview_prep", 1)

    job = app_row.job
    try:
        brief = interview_prep_service.generate_prep_brief(
            user.resume_text,
            {"title": job.title, "company": job.company, "description": job.description},
        )
    except Exception:
        usage.decrement(db, user.id, "interview_prep", 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't generate interview prep right now — this attempt wasn't counted against your limit. Try again shortly.",
        )

    prep = models.InterviewPrep(application_id=application_id, user_id=user.id, brief=brief)
    db.add(prep)
    db.commit()
    db.refresh(prep)
    rise_index.award_points(db, user, "generate_interview_prep", "Prepped for an interview")
    return prep


@router.get("/{application_id}/interview-prep", response_model=schemas.InterviewPrepOut)
def get_interview_prep(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _get_owned_application(db, application_id, user.id)
    prep = db.query(models.InterviewPrep).filter_by(application_id=application_id).first()
    if not prep:
        raise HTTPException(status_code=404, detail="No interview prep generated yet.")
    return prep
