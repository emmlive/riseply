from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import progress as progress_service

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("", response_model=schemas.ProgressOut)
def get_progress(
    tz_offset: int = Query(0, ge=-840, le=840, description="Browser getTimezoneOffset(), so weeks start on the person's Monday"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The person's own progress: Career Coach scores and the job-search funnel.
    Read-only and computed from existing rows; costs no AI calls and is not metered."""
    return progress_service.build_progress(db, user, tz_offset=tz_offset)
