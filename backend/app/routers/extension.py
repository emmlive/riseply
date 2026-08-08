"""
Backend surface for the Riseply browser extension. Currently just one
endpoint: score whatever job the person is actually looking at right
now, on whatever site they're on -- which may not be anything in
Riseply's own discovered job pool (that pool only covers Greenhouse/
Lever/RSS sources; the extension needs to work on any job site).

Scored the same way as regular matching (same matcher.score_job/
best_profile_match, same Claude call), just against ad-hoc scraped
text instead of a Job row from the database, and metered against the
same "match" usage quota so this doesn't become a free side door
around the monthly limit.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app.services import matcher, usage
from app import models, schemas

router = APIRouter(prefix="/extension", tags=["extension"])


@router.post("/score-job", response_model=schemas.ExtensionScoreResponse)
def score_job_ad_hoc(
    payload: schemas.ExtensionScoreRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume in Riseply before scoring jobs.")

    usage.check_and_increment(db, user, "match", 1)

    job = {
        "title": payload.title, "company": payload.company,
        "location": payload.location, "description": payload.description,
    }

    profiles_rows = db.query(models.SearchProfile).filter_by(user_id=user.id, active=True).all()

    try:
        if profiles_rows:
            profiles = [{
                "name": p.name, "titles": json.loads(p.titles), "locations": json.loads(p.locations),
                "seniority": json.loads(p.seniority), "min_match_score": p.min_match_score,
                "exclude_companies": json.loads(p.exclude_companies),
                "keywords_required": json.loads(p.keywords_required),
                "keywords_excluded": json.loads(p.keywords_excluded), "active": p.active,
            } for p in profiles_rows]
            best = matcher.best_profile_match(job, user.resume_text, profiles)
            return schemas.ExtensionScoreResponse(
                score=best["score"], reason=best["reason"], matched_profile=best["profile_name"],
            )
        else:
            # No saved search profiles yet -- still score against just
            # the resume with a generic, no-frills criteria set rather
            # than requiring profile setup before the extension does
            # anything at all.
            result = matcher.score_job(user.resume_text, job, {"min_match_score": 60})
            return schemas.ExtensionScoreResponse(score=result["score"], reason=result["reason"], matched_profile=None)
    except Exception as e:
        usage.decrement(db, user.id, "match", 1)
        print(f"[extension] Ad-hoc scoring failed for user {user.id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't score this job right now — try again shortly.")
