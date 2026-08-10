"""
Multiple resumes per user, one marked default.

User.resume_text (the field every other part of the app -- matching,
tailoring, interview prep, the extension's scoring and autofill --
already reads directly) is deliberately left completely alone and
untouched by this feature. Instead, _sync_default_to_user() below is
the ONE place responsible for keeping it mirrored to whichever Resume
row is currently is_default, called after every operation that could
change which resume that is (create-as-first, set-default, edit-the-
default, delete-the-default). Every other consumer across the app
keeps working exactly as it did before this feature existed, with zero
changes needed anywhere else.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app import models, schemas

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _sync_default_to_user(db: Session, user: models.User):
    default = db.query(models.Resume).filter_by(user_id=user.id, is_default=True).first()
    user.resume_text = default.resume_text if default else ""
    db.commit()


@router.get("", response_model=list[schemas.SavedResumeOut])
def list_resumes(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Resume)
        .filter_by(user_id=user.id)
        .order_by(models.Resume.is_default.desc(), models.Resume.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.SavedResumeOut)
def create_resume(
    payload: schemas.SavedResumeCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    existing_count = db.query(models.Resume).filter_by(user_id=user.id).count()
    resume = models.Resume(
        user_id=user.id,
        label=payload.label.strip() or f"Resume {existing_count + 1}",
        resume_text=payload.resume_text,
        is_default=(existing_count == 0),  # the very first resume a user adds is automatically their default
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    if resume.is_default:
        _sync_default_to_user(db, user)
    return resume


@router.patch("/{resume_id}", response_model=schemas.SavedResumeOut)
def update_resume(
    resume_id: int,
    payload: schemas.SavedResumeUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    resume = db.query(models.Resume).filter_by(id=resume_id, user_id=user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    if payload.label is not None:
        resume.label = payload.label.strip()
    if payload.resume_text is not None:
        resume.resume_text = payload.resume_text
    db.commit()
    db.refresh(resume)

    if resume.is_default and payload.resume_text is not None:
        _sync_default_to_user(db, user)
    return resume


@router.post("/{resume_id}/set-default", response_model=schemas.SavedResumeOut)
def set_default_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    resume = db.query(models.Resume).filter_by(id=resume_id, user_id=user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    db.query(models.Resume).filter_by(user_id=user.id, is_default=True).update({"is_default": False})
    resume.is_default = True
    db.commit()
    db.refresh(resume)
    _sync_default_to_user(db, user)
    return resume


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    resume = db.query(models.Resume).filter_by(id=resume_id, user_id=user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    was_default = resume.is_default
    db.delete(resume)
    db.commit()

    if was_default:
        # Promote whichever resume was created most recently among
        # whatever's left, so the account always has SOME default as
        # long as it has any resume at all -- rather than silently
        # leaving every remaining resume non-default and every matching/
        # tailoring/extension call operating on a blank resume until
        # someone notices and picks a new one manually.
        next_default = (
            db.query(models.Resume).filter_by(user_id=user.id)
            .order_by(models.Resume.created_at.desc()).first()
        )
        if next_default:
            next_default.is_default = True
            db.commit()
        _sync_default_to_user(db, user)

    return {"deleted": True}
