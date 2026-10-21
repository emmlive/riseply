from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import job_terms, resume_customizer, resume_facts

# Helps a tailored resume get past screens: shows which of the posting's key
# terms and hard requirements the resume covers (no AI, free), and lets the
# person add real experience the resume leaves out.
router = APIRouter(tags=["resume-check"])


@router.get("/applications/{application_id}/resume-check", response_model=schemas.ResumeCheckOut)
def resume_check(application_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    if not app_row.tailored_resume_data:
        raise HTTPException(status_code=404, detail="Tailor your resume for this job first.")
    job = db.get(models.Job, app_row.job_id)
    try:
        tailored = resume_customizer._all_text(resume_customizer.docx_to_blocks(app_row.tailored_resume_data))
    except Exception:
        raise HTTPException(status_code=422, detail="This tailored resume couldn't be read.")
    desc = (job.description if job else "") or ""
    cov = job_terms.coverage(desc, user.resume_text or "", tailored)
    return schemas.ResumeCheckOut(
        **cov,
        checks=job_terms.screening_checks(desc, tailored, datetime.utcnow().year),
        facts=[schemas.ResumeFactOut(id=f.id, skill=f.skill, detail=f.detail)
               for f in db.query(models.ResumeFact).filter_by(user_id=user.id).order_by(models.ResumeFact.id).all()],
    )


class FactIn(BaseModel):
    skill: str = Field(min_length=2, max_length=60)
    detail: str = Field(min_length=8, max_length=240)


@router.post("/resume-facts", response_model=schemas.ResumeFactOut)
def add_fact(payload: FactIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = resume_facts.add(db, user.id, payload.skill, payload.detail)
    if not row:
        raise HTTPException(status_code=400, detail=f"Add a skill and a sentence about it (you can keep up to {resume_facts.MAX_FACTS}).")
    return schemas.ResumeFactOut(id=row.id, skill=row.skill, detail=row.detail)


@router.delete("/resume-facts/{fact_id}")
def delete_fact(fact_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.query(models.ResumeFact).filter_by(id=fact_id, user_id=user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}
