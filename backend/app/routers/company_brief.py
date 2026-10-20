import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import company_brief as brief_service
from app.services import usage

# One-page brief on the company and role for an application. Written once and
# saved; re-running is explicit and metered, with a refund on failure.
router = APIRouter(prefix="/applications", tags=["company-brief"])

ACTION = "company_brief"


@router.post("/{application_id}/company-brief", response_model=schemas.CompanyBriefOut)
def company_brief(
    application_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    if app_row.company_brief_data and not refresh:
        try:
            return schemas.CompanyBriefOut(**json.loads(app_row.company_brief_data), cached=True)
        except Exception:
            pass  # unreadable saved copy: fall through and rewrite

    job = db.get(models.Job, app_row.job_id)
    job_dict = {"title": job.title, "company": job.company, "description": job.description,
                "location": getattr(job, "location", "") or ""}

    usage.check_and_increment(db, user, ACTION, 1)
    try:
        result = brief_service.write(user.resume_text or "", job_dict)
    except Exception:
        usage.decrement(db, user.id, ACTION, 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't write the brief right now -- this attempt wasn't counted against your limit. Try again shortly.",
        )

    app_row.company_brief_data = json.dumps(result)
    db.commit()
    return schemas.CompanyBriefOut(**result)
