from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import rise_index

router = APIRouter(prefix="/rise-index", tags=["rise-index"])


@router.get("/trending", response_model=list[schemas.CompanyStatsOut])
def get_trending(
    days: int = 14,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return rise_index.trending_companies(db, days=days)


@router.get("/company-stats", response_model=schemas.CompanyStatsOut)
def get_company_stats(
    company: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stats = rise_index.company_stats(db, company)
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="Not enough data yet for this company — needs a few more applicants before we can show a reliable stat.",
        )
    return stats


@router.get("/me", response_model=schemas.RiseIndexMeOut)
def get_my_rise_index(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    events = db.query(models.PointsEvent).filter_by(user_id=user.id).order_by(
        models.PointsEvent.created_at.desc()
    ).limit(15).all()
    return schemas.RiseIndexMeOut(
        rise_points=user.rise_points,
        current_streak=user.current_streak,
        longest_streak=user.longest_streak,
        recent_events=events,
    )
