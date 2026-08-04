import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _to_out(p: models.SearchProfile) -> schemas.SearchProfileOut:
    return schemas.SearchProfileOut(
        id=p.id,
        name=p.name,
        titles=json.loads(p.titles),
        locations=json.loads(p.locations),
        seniority=json.loads(p.seniority),
        min_match_score=p.min_match_score,
        exclude_companies=json.loads(p.exclude_companies),
        keywords_required=json.loads(p.keywords_required),
        keywords_excluded=json.loads(p.keywords_excluded),
        active=p.active,
    )


@router.get("", response_model=list[schemas.SearchProfileOut])
def list_profiles(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.SearchProfile).filter_by(user_id=user.id).all()
    return [_to_out(p) for p in rows]


@router.post("", response_model=schemas.SearchProfileOut)
def create_profile(
    payload: schemas.SearchProfileIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = models.SearchProfile(
        user_id=user.id,
        name=payload.name,
        titles=json.dumps(payload.titles),
        locations=json.dumps(payload.locations),
        seniority=json.dumps(payload.seniority),
        min_match_score=payload.min_match_score,
        exclude_companies=json.dumps(payload.exclude_companies),
        keywords_required=json.dumps(payload.keywords_required),
        keywords_excluded=json.dumps(payload.keywords_excluded),
        active=payload.active,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.put("/{profile_id}", response_model=schemas.SearchProfileOut)
def update_profile(
    profile_id: int,
    payload: schemas.SearchProfileIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(models.SearchProfile).filter_by(id=profile_id, user_id=user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")

    p.name = payload.name
    p.titles = json.dumps(payload.titles)
    p.locations = json.dumps(payload.locations)
    p.seniority = json.dumps(payload.seniority)
    p.min_match_score = payload.min_match_score
    p.exclude_companies = json.dumps(payload.exclude_companies)
    p.keywords_required = json.dumps(payload.keywords_required)
    p.keywords_excluded = json.dumps(payload.keywords_excluded)
    p.active = payload.active
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(models.SearchProfile).filter_by(id=profile_id, user_id=user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(p)
    db.commit()
    return {"deleted": True}
