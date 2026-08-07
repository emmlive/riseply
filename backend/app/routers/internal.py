from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app import models
from app.services import pipeline_runner

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/scheduled-run")
def scheduled_run(
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Meant to be called by an external scheduler (GitHub Actions cron,
    cron-job.org, etc.) once a day -- see README for setup. Not tied to
    any single user's session; runs discovery once, then matching for
    every user who has a resume and at least one active search profile.

    Protected by a shared secret rather than a login, since there's no
    user to log in as for a background job. Blank CRON_SECRET disables
    the endpoint entirely (503) rather than defaulting to open."""
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail="Scheduled matching isn't configured (CRON_SECRET unset).")
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid cron secret.")

    discovery_result = pipeline_runner.run_discovery(db)

    users = db.query(models.User).filter(models.User.resume_text.isnot(None)).all()
    per_user_results = {}
    for user in users:
        if not user.resume_text or not user.resume_text.strip():
            continue
        has_active_profile = db.query(models.SearchProfile).filter_by(
            user_id=user.id, active=True
        ).first()
        if not has_active_profile:
            continue

        try:
            result = pipeline_runner.run_matching_for_user(db, user)
            per_user_results[user.email] = {
                "queued": len(result["queued_application_ids"]),
                "usage_limit_reached": result["usage_limit_reached"],
            }
        except Exception as e:
            # One user's failure (e.g. a transient DB issue mid-loop)
            # shouldn't stop the rest of the batch from running.
            per_user_results[user.email] = {"error": str(e)}

    return {
        "discovery": discovery_result,
        "users_processed": len(per_user_results),
        "results": per_user_results,
    }


@router.post("/culture-bot-run")
def culture_bot_run(
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Meant to be called by an external scheduler once a day, same
    pattern and same CRON_SECRET as /internal/scheduled-run above --
    see README's 'Culture Bot lessons' section for setup. Sends any
    org onboarding lessons due today by email, and any quiz reminders
    due a week after a wrong answer."""
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail="Culture Bot isn't configured (CRON_SECRET unset).")
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid cron secret.")

    from app.services import culture_bot
    return culture_bot.run_deliveries(db)
