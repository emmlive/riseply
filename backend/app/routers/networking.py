import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import networking as networking_service
from app.services import usage

# Networking drafts for one application. Written once and saved; writing
# again (or for a named contact) is explicit and metered. Nothing is sent
# anywhere -- the person copies each message and sends it themselves.
router = APIRouter(prefix="/applications", tags=["networking"])

ACTION = "networking"


@router.post("/{application_id}/networking", response_model=schemas.NetworkingOut)
def networking(
    application_id: int,
    payload: schemas.NetworkingRequest | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    payload = payload or schemas.NetworkingRequest()
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user.id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    custom = bool(payload.contact_name or payload.contact_role)
    if app_row.networking_data and not payload.refresh and not custom:
        try:
            return schemas.NetworkingOut(**json.loads(app_row.networking_data), cached=True)
        except Exception:
            pass  # unreadable saved copy: fall through and rewrite

    if not (user.resume_text or "").strip():
        raise HTTPException(status_code=400, detail="Add your resume first -- the messages are written from it.")

    job = db.get(models.Job, app_row.job_id)
    job_dict = {"title": job.title, "company": job.company, "description": job.description}

    usage.check_and_increment(db, user, ACTION, 1)
    try:
        result = networking_service.write(user.resume_text, job_dict, payload.contact_name, payload.contact_role)
    except Exception:
        usage.decrement(db, user.id, ACTION, 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't write the messages right now -- this attempt wasn't counted against your limit. Try again shortly.",
        )

    app_row.networking_data = json.dumps(result)
    db.commit()
    return schemas.NetworkingOut(**result)
