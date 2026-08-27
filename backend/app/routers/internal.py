import json

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app import models
from app.services import pipeline_runner

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_cron_secret(x_cron_secret: str, unconfigured_detail: str) -> None:
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail=unconfigured_detail)
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid cron secret.")


@router.post("/scheduled-run")
def scheduled_run(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Meant to be called by an external scheduler (GitHub Actions cron,
    cron-job.org, etc.) once a day -- see README for setup. Not tied to
    any single user's session; runs discovery once, then matching for
    every user who has a resume and at least one active search profile.

    Protected by a shared secret rather than a login, since there's no
    user to log in as for a background job. Blank CRON_SECRET disables
    the endpoint entirely (503) rather than defaulting to open.

    Returns 202 immediately with a run_id rather than blocking until
    the batch finishes. The actual discovery+matching work (one Claude
    API call per unseen job per user, uncapped for this scheduled path
    -- see run_matching_for_user's docstring) can legitimately take a
    long time for a real user base, and used to run inline in this
    request -- which meant the triggering GitHub Actions curl call sat
    on a single open connection for as long as that took, at the mercy
    of any proxy/timeout along the way. Poll GET /internal/scheduled-run/
    {run_id} (same header) for status."""
    _check_cron_secret(x_cron_secret, "Scheduled matching isn't configured (CRON_SECRET unset).")

    log = models.ScheduledRunLog(run_type="scheduled_run", status="running")
    db.add(log)
    db.commit()
    db.refresh(log)

    background_tasks.add_task(pipeline_runner.run_scheduled_matching_background, log.id)

    return JSONResponse(status_code=202, content={"status": "started", "run_id": log.id})


@router.get("/scheduled-run/{run_id}")
def scheduled_run_status(
    run_id: int,
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Polled by the external scheduler after POST /internal/scheduled-run
    returns 202, to find out when the background batch actually
    finishes and whether it succeeded. Same secret gate as the other
    /internal/* endpoints -- this exposes per-user email addresses and
    match counts in result_json, not something to leave open."""
    _check_cron_secret(x_cron_secret, "Scheduled matching isn't configured (CRON_SECRET unset).")

    log = db.get(models.ScheduledRunLog, run_id)
    if log is None:
        raise HTTPException(status_code=404, detail="No run with that id.")

    return {
        "run_id": log.id,
        "status": log.status,
        "result": json.loads(log.result_json) if log.result_json else None,
        "error": log.error,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
    }


@router.post("/culture-bot-run")
def culture_bot_run(
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Meant to be called by an external scheduler once a day, same
    pattern and same CRON_SECRET as /internal/scheduled-run above --
    see README's 'Culture Bot lessons' section for setup. Sends any
    org onboarding lessons due today by email, any quiz reminders due
    a week after a wrong answer, and mentorship check-in nudges for
    pairings that have gone quiet.

    Mentorship reminders run here rather than getting their own
    endpoint/workflow: both this and culture bot lessons are
    org-onboarding-context daily emails, both are fast (no per-job
    Claude scoring loop the way scheduled-run has), and this endpoint
    already has a proven-reliable daily cron trigger -- no reason to
    stand up parallel infrastructure for something that fits the
    existing one."""
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail="Culture Bot isn't configured (CRON_SECRET unset).")
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid cron secret.")

    from app.services import culture_bot, mentor_reminders
    result = culture_bot.run_deliveries(db)
    result.update(mentor_reminders.run_mentorship_reminders(db))
    return result


@router.post("/send-digests")
def send_digests(
    db: Session = Depends(get_db),
    x_cron_secret: str = Header(default=""),
):
    """Sends the daily digest email to every user on
    notification_preference='daily_digest' -- meant to run once a day,
    after /internal/scheduled-run has finished matching, via the same
    external scheduler and CRON_SECRET as the other /internal/* jobs."""
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail="Digests aren't configured (CRON_SECRET unset).")
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid cron secret.")

    return pipeline_runner.send_daily_digests(db)
