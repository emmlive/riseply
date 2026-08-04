from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import job_buddy as job_buddy_service
from app.services import usage, rise_index

router = APIRouter(prefix="/applications", tags=["job-buddy"])


def _get_owned_application(db: Session, application_id: int, user_id: int) -> models.Application:
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user_id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_row


@router.post("/{application_id}/onboarding-plan", response_model=schemas.OnboardingPlanOut)
def generate_onboarding_plan(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)

    existing = db.query(models.OnboardingPlan).filter_by(application_id=application_id).first()
    if existing:
        return existing

    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume before generating an onboarding plan.")

    usage.check_and_increment(db, user.id, "onboarding_plan", 1)
    job = app_row.job
    try:
        plan_text = job_buddy_service.generate_onboarding_plan(
            user.resume_text,
            {"title": job.title, "company": job.company, "description": job.description},
        )
    except Exception:
        usage.decrement(db, user.id, "onboarding_plan", 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't generate your onboarding plan right now — this attempt wasn't counted against your limit. Try again shortly.",
        )

    plan = models.OnboardingPlan(application_id=application_id, user_id=user.id, plan=plan_text)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    rise_index.award_points(db, user, "generate_onboarding_plan", "Built an onboarding plan")
    return plan


@router.get("/{application_id}/onboarding-plan", response_model=schemas.OnboardingPlanOut)
def get_onboarding_plan(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _get_owned_application(db, application_id, user.id)
    plan = db.query(models.OnboardingPlan).filter_by(application_id=application_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="No onboarding plan generated yet.")
    return plan


@router.get("/{application_id}/job-buddy/messages", response_model=list[schemas.JobBuddyMessageOut])
def get_job_buddy_messages(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _get_owned_application(db, application_id, user.id)
    return db.query(models.JobBuddyMessage).filter_by(
        application_id=application_id, user_id=user.id
    ).order_by(models.JobBuddyMessage.created_at.asc()).all()


@router.post("/{application_id}/job-buddy/messages", response_model=schemas.JobBuddyMessageOut)
def send_job_buddy_message(
    application_id: int,
    payload: schemas.JobBuddyChatRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)

    plan = db.query(models.OnboardingPlan).filter_by(application_id=application_id).first()
    if not plan:
        raise HTTPException(
            status_code=400,
            detail="Generate an onboarding plan first — Job Buddy uses it as context.",
        )

    usage.check_and_increment(db, user.id, "job_buddy_message", 1)

    history_rows = db.query(models.JobBuddyMessage).filter_by(
        application_id=application_id, user_id=user.id
    ).order_by(models.JobBuddyMessage.created_at.asc()).all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    user_msg = models.JobBuddyMessage(
        application_id=application_id, user_id=user.id, role="user", content=payload.message,
    )
    db.add(user_msg)
    db.commit()

    job = app_row.job
    try:
        reply_text = job_buddy_service.chat_reply(
            user.resume_text,
            {"title": job.title, "company": job.company, "description": job.description},
            plan.plan,
            history,
            payload.message,
        )
    except Exception:
        usage.decrement(db, user.id, "job_buddy_message", 1)
        raise HTTPException(
            status_code=502,
            detail="Job Buddy couldn't respond right now — this attempt wasn't counted against your limit. Your message was saved; try sending again.",
        )

    reply_msg = models.JobBuddyMessage(
        application_id=application_id, user_id=user.id, role="assistant", content=reply_text,
    )
    db.add(reply_msg)
    db.commit()
    db.refresh(reply_msg)
    rise_index.award_points(db, user, "job_buddy_message", "Chatted with Job Buddy")
    return reply_msg
