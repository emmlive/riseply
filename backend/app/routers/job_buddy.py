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


def _org_content_for(db: Session, app_row: models.Application) -> str:
    """Concatenates an org's uploaded custom content for use in prompts.
    Empty string if this application isn't linked to an org -- the
    service functions treat that as 'no custom content' and fall back
    to generic advice, same as before this feature existed."""
    if not app_row.organization_id:
        return ""
    rows = db.query(models.OrganizationBuddyContent).filter_by(
        organization_id=app_row.organization_id
    ).all()
    return "\n\n".join(f"[{r.title}]\n{r.content}" for r in rows)


@router.post("/current-job", response_model=schemas.ApplicationOut)
def add_current_job(
    payload: schemas.AddCurrentJobRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Lets a user unlock Job Buddy for a job they already have, without
    going through Riseply's own discovery/matching pipeline at all --
    someone who found their job elsewhere (or has had it for years)
    shouldn't need a fake 'match' to get ongoing mentor support.

    An optional org_join_code links this to a company's "Org Buddy as a
    Service" account -- the plan/chat then draws on that org's uploaded
    custom content too. An invalid code is a clean 400, not a silent
    no-op, so a typo doesn't quietly lose the org context."""
    organization_id = None
    company = payload.company
    title = payload.title
    tenure = payload.tenure

    if payload.org_join_code:
        org = db.query(models.Organization).filter_by(join_code=payload.org_join_code.upper()).first()
        if not org:
            raise HTTPException(status_code=400, detail="That organization join code isn't valid.")
        organization_id = org.id
        company = org.name  # the org IS the company -- no need to re-type it

        already_member = db.query(models.OrganizationMember).filter_by(
            organization_id=org.id, user_id=user.id
        ).first()
        if not already_member:
            db.add(models.OrganizationMember(organization_id=org.id, user_id=user.id, role="employee"))
            db.commit()

        # If the org admin pre-registered this person via CSV roster
        # upload, use their real title/tenure instead of asking the
        # employee to hand-type it again -- and mark the roster entry as
        # matched, which is what makes it show up as "joined" in the
        # admin's roster view.
        roster_entry = db.query(models.OrgRosterEntry).filter_by(
            organization_id=org.id, email=user.email
        ).first()
        if roster_entry:
            if roster_entry.title:
                title = roster_entry.title
            tenure = roster_entry.tenure
            roster_entry.matched_user_id = user.id
            db.commit()

    import time
    job = models.Job(
        source="manual", external_id=f"manual-{user.id}-{int(time.time() * 1000)}",
        company=company, title=title, location="",
        url="", description=payload.description,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    application = models.Application(
        user_id=user.id, job_id=job.id,
        matched_profile="", match_score=0,
        match_reason="Added manually — an existing job, not matched through Riseply.",
        status="accepted", tenure_hint=tenure, organization_id=organization_id,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    from app.routers.pipeline import _to_out
    return _to_out(application, job)


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

    usage.check_and_increment(db, user, "onboarding_plan", 1)
    job = app_row.job
    try:
        plan_text = job_buddy_service.generate_onboarding_plan(
            user.resume_text,
            {"title": job.title, "company": job.company, "description": job.description},
            tenure=app_row.tenure_hint or "just_started",
            org_content=_org_content_for(db, app_row),
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

    usage.check_and_increment(db, user, "job_buddy_message", 1)

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
            tenure=app_row.tenure_hint or "just_started",
            org_content=_org_content_for(db, app_row),
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
