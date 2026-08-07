from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import job_buddy as job_buddy_service
from app.services import usage, rise_index, notifier
from app.routers.org_buddy import resolve_join_code

router = APIRouter(prefix="/applications", tags=["job-buddy"])


def _get_owned_application(db: Session, application_id: int, user_id: int) -> models.Application:
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user_id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_row


def _org_content_for(db: Session, app_row: models.Application) -> str:
    """Concatenates an org's uploaded custom content AND human contacts
    for use in prompts -- company-wide material plus (if this employee
    belongs to a department) that department's own content layered on
    top. Empty string if this application isn't linked to an org -- the
    service functions treat that as 'no custom content' and fall back
    to generic advice, same as before this feature existed."""
    if not app_row.organization_id:
        return ""

    content_q = db.query(models.OrganizationBuddyContent).filter_by(organization_id=app_row.organization_id)
    if app_row.department_id:
        content_q = content_q.filter(
            (models.OrganizationBuddyContent.department_id == None)  # noqa: E711
            | (models.OrganizationBuddyContent.department_id == app_row.department_id)
        )
    else:
        content_q = content_q.filter(models.OrganizationBuddyContent.department_id == None)  # noqa: E711
    parts = [f"[{r.title}]\n{r.content}" for r in content_q.all()]

    contacts_q = db.query(models.OrgHumanContact).filter_by(organization_id=app_row.organization_id)
    if app_row.department_id:
        contacts_q = contacts_q.filter(
            (models.OrgHumanContact.department_id == None)  # noqa: E711
            | (models.OrgHumanContact.department_id == app_row.department_id)
        )
    else:
        contacts_q = contacts_q.filter(models.OrgHumanContact.department_id == None)  # noqa: E711
    contacts = contacts_q.all()
    if contacts:
        contact_lines = "\n".join(f"- {c.name} ({c.email}): {c.description}" for c in contacts)
        parts.append(
            "[People at this company who can help with things you (the AI) can't do "
            "directly, like an office tour or a face-to-face intro -- mention the right "
            "one by name when it's relevant, and let the person know they can use the "
            "\"Request a handoff\" option to actually connect]\n" + contact_lines
        )

    return "\n\n".join(parts)


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
    Service" account. The code can be either the org-wide code (company-
    wide content only) or a specific department's code (company-wide
    content plus that department's own material). An invalid code is a
    clean 400, not a silent no-op, so a typo doesn't quietly lose the
    org context."""
    organization_id = None
    department_id = None
    company = payload.company
    title = payload.title
    tenure = payload.tenure

    if payload.org_join_code:
        organization_id, department_id = resolve_join_code(db, payload.org_join_code)
        org = db.query(models.Organization).filter_by(id=organization_id).first()
        company = org.name  # the org IS the company -- no need to re-type it

        already_member = db.query(models.OrganizationMember).filter_by(
            organization_id=organization_id, user_id=user.id
        ).first()
        if not already_member:
            db.add(models.OrganizationMember(
                organization_id=organization_id, user_id=user.id, role="employee", department_id=department_id,
            ))
            db.commit()

        # If the org admin pre-registered this person via CSV roster
        # upload, use their real title/tenure instead of asking the
        # employee to hand-type it again -- and mark the roster entry as
        # matched, which is what makes it show up as "joined" in the
        # admin's roster view. The roster entry's own department (if the
        # admin set one) takes precedence over whatever code the
        # employee happened to use, since it reflects what the admin
        # actually knows about their real department assignment.
        roster_entry = db.query(models.OrgRosterEntry).filter_by(
            organization_id=organization_id, email=user.email
        ).first()
        if roster_entry:
            if roster_entry.title:
                title = roster_entry.title
            tenure = roster_entry.tenure
            if roster_entry.department_id is not None:
                department_id = roster_entry.department_id
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
        status="accepted", tenure_hint=tenure, organization_id=organization_id, department_id=department_id,
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


# --- Handoff to a real human (things AI structurally can't do) ---

@router.get("/{application_id}/handoff-contacts", response_model=list[schemas.OrgContactOut])
def get_handoff_contacts(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    if not app_row.organization_id:
        return []  # not an org-linked job -- no company contacts to hand off to
    return db.query(models.OrgHumanContact).filter_by(organization_id=app_row.organization_id).all()


@router.post("/{application_id}/handoff")
def request_handoff(
    application_id: int,
    payload: schemas.HandoffRequestCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Sends the employee's own note (never their Job Buddy chat history)
    to a real contact at their company. This is what keeps the handoff
    consistent with the privacy model established for Org Buddy: the
    employee decides exactly what leaves their private conversation, in
    their own words -- nothing here is an AI-generated summary of what
    they've been discussing."""
    app_row = _get_owned_application(db, application_id, user.id)
    if not app_row.organization_id:
        raise HTTPException(status_code=400, detail="This job isn't linked to an organization.")

    contact = db.query(models.OrgHumanContact).filter_by(
        id=payload.contact_id, organization_id=app_row.organization_id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")

    job = app_row.job
    try:
        notifier.send_email(
            contact.email,
            f"[Riseply] {user.full_name or user.email} would like to connect",
            (
                f"{user.full_name or '(no name given)'} ({user.email}), "
                f"{job.title} at {job.company}, would like to connect with you"
                f"{f' — {contact.description}' if contact.description else ''}.\n\n"
                f"Their note:\n{payload.note}"
            ),
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Couldn't send that right now — try again shortly.",
        )

    handoff = models.HandoffRequest(
        application_id=application_id, organization_id=app_row.organization_id,
        contact_id=contact.id, note=payload.note,
    )
    db.add(handoff)
    db.commit()
    return {"sent": True, "contact_name": contact.name}
