from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=schemas.UserOut)
def get_me(user: models.User = Depends(get_current_user)):
    return user


@router.patch("", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.put("/resume", response_model=schemas.UserOut)
def update_resume(
    payload: schemas.ResumeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.resume_text = payload.resume_text
    db.commit()
    db.refresh(user)
    return user
