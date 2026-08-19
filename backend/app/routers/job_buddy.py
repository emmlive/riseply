from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import job_buddy as job_buddy_service
from app.services import usage, rise_index, notifier, safety_flags
from app.services import kb as kb_service
from app.routers.org_buddy import resolve_join_code

router = APIRouter(prefix="/applications", tags=["job-buddy"])


def _get_owned_application(db: Session, application_id: int, user_id: int) -> models.Application:
    app_row = db.query(models.Application).filter_by(id=application_id, user_id=user_id).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_row


def _org_content_items(db: Session, app_row: models.Application) -> list[models.OrganizationBuddyContent]:
    """Company-wide content plus (if this employee belongs to a
    department) that department's own content layered on top. Empty
    list if this application isn't linked to an org. Returns the raw
    ORM rows (not concatenated text) so callers can do retrieval-scoped
    selection over individual items -- see _org_content_for below for
    the 'just give me everything as one blob' version used by the
    onboarding-plan/chat prompts."""
    if not app_row.organization_id:
        return []

    content_q = db.query(models.OrganizationBuddyContent).filter_by(organization_id=app_row.organization_id)
    if app_row.department_id:
        content_q = content_q.filter(
            (models.OrganizationBuddyContent.department_id == None)  # noqa: E711
            | (models.OrganizationBuddyContent.department_id == app_row.department_id)
        )
    else:
        content_q = content_q.filter(models.OrganizationBuddyContent.department_id == None)  # noqa: E711
    return content_q.all()


def _org_content_for(db: Session, app_row: models.Application) -> str:
    """Concatenates an org's uploaded custom content AND human contacts
    for use in prompts -- company-wide material plus (if this employee
    belongs to a department) that department's own content layered on
    top. Empty string if this application isn't linked to an org -- the
    service functions treat that as 'no custom content' and fall back
    to generic advice, same as before this feature existed."""
    if not app_row.organization_id:
        return ""

    parts = [f"[{r.title}]\n{r.content}" for r in _org_content_items(db, app_row)]

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
    manager_email = ""
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
        # upload, use their real title/tenure/manager instead of asking
        # the employee to hand-type it again -- and mark the roster
        # entry as matched, which is what makes it show up as "joined"
        # in the admin's roster view. The roster entry's own department
        # (if the admin set one) takes precedence over whatever code the
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
            manager_email = roster_entry.manager_email
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
        department_id=department_id, manager_email=manager_email,
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

    user_flag = safety_flags.scan(payload.message)
    user_msg = models.JobBuddyMessage(
        application_id=application_id, user_id=user.id, role="user", content=payload.message,
        flagged=bool(user_flag), flag_reason=user_flag,
    )
    db.add(user_msg)
    db.commit()

    job = app_row.job
    career_goals = [
        g.goal_text for g in db.query(models.CareerGoal)
        .filter_by(application_id=application_id, achieved_at=None)
        .order_by(models.CareerGoal.created_at.desc()).all()
    ]
    try:
        reply_text = job_buddy_service.chat_reply(
            user.resume_text,
            {"title": job.title, "company": job.company, "description": job.description},
            plan.plan,
            history,
            payload.message,
            tenure=app_row.tenure_hint or "just_started",
            org_content=_org_content_for(db, app_row),
            career_goals=career_goals,
        )
    except Exception as e:
        usage.decrement(db, user.id, "job_buddy_message", 1)
        print(f"[job_buddy] Chat reply generation failed for application {application_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Job Buddy couldn't respond right now — this attempt wasn't counted against your limit. Your message was saved; try sending again.",
        )

    reply_flag = safety_flags.scan(reply_text)
    reply_msg = models.JobBuddyMessage(
        application_id=application_id, user_id=user.id, role="assistant", content=reply_text,
        flagged=bool(reply_flag), flag_reason=reply_flag,
    )
    db.add(reply_msg)
    db.commit()
    db.refresh(reply_msg)
    rise_index.award_points(db, user, "job_buddy_message", "Chatted with Job Buddy")
    return reply_msg


# --- Instant company Q&A ("Ghost Onboarder") ---
#
# Distinct from the Job Buddy chat above: this doesn't need an
# onboarding plan generated first, isn't a running conversation, and
# only ever answers from the org's own uploaded content (retrieved for
# this specific question, not the whole library) rather than reasoning
# generally about the role. It's meant for quick factual lookups
# ("where do I request PTO", "who do I ask about my laptop") rather
# than the ongoing coaching Job Buddy does.

@router.post("/{application_id}/org-ask", response_model=schemas.OrgAskResponse)
def ask_org_question(
    application_id: int,
    payload: schemas.OrgAskRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    if not app_row.organization_id:
        raise HTTPException(
            status_code=400,
            detail="This job isn't linked to a company account, so there's no company content to search yet.",
        )

    usage.check_and_increment(db, user, "org_ask", 1)

    org = db.query(models.Organization).filter_by(id=app_row.organization_id).first()
    items = _org_content_items(db, app_row)
    relevant = kb_service.retrieve_relevant_org_content(payload.question, items)

    try:
        answer = kb_service.answer_org_question(payload.question, org.name, relevant)
    except Exception:
        usage.decrement(db, user.id, "org_ask", 1)
        raise HTTPException(
            status_code=502,
            detail="Couldn't get an answer right now — this attempt wasn't counted against your limit. Try again shortly.",
        )

    db.add(models.OrgQALog(
        organization_id=app_row.organization_id, application_id=application_id, user_id=user.id,
        question=payload.question, answer=answer, matched_content=bool(relevant),
    ))
    db.commit()

    return schemas.OrgAskResponse(answer=answer, sources=[i.title for i in relevant])


# --- Culture Bot: this employee's delivered lessons ---

@router.get("/{application_id}/lessons", response_model=list[schemas.LessonDeliveryOut])
def list_my_lessons(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    rows = (
        db.query(models.LessonDelivery, models.OrgLesson)
        .join(models.OrgLesson, models.LessonDelivery.lesson_id == models.OrgLesson.id)
        .filter(models.LessonDelivery.application_id == application_id)
        .order_by(models.LessonDelivery.delivered_at.desc())
        .all()
    )
    return [
        schemas.LessonDeliveryOut(
            id=delivery.id, lesson_id=lesson.id, title=lesson.title, content=lesson.content,
            quiz_question=lesson.quiz_question, media_url=lesson.media_url or "",
            delivered_at=delivery.delivered_at,
            quiz_response=delivery.quiz_response, quiz_correct=delivery.quiz_correct,
        )
        for delivery, lesson in rows
    ]


@router.post("/{application_id}/lessons/{delivery_id}/quiz-response")
def submit_lesson_quiz_response(
    application_id: int,
    delivery_id: int,
    payload: schemas.LessonQuizResponseRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services import culture_bot

    _get_owned_application(db, application_id, user.id)
    delivery = db.query(models.LessonDelivery).filter_by(id=delivery_id, application_id=application_id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Lesson delivery not found.")

    lesson = db.query(models.OrgLesson).filter_by(id=delivery.lesson_id).first()
    if not lesson or not lesson.quiz_question:
        raise HTTPException(status_code=400, detail="This lesson doesn't have a quiz to answer.")

    delivery.quiz_response = payload.response
    delivery.quiz_correct = culture_bot.grade_quiz(lesson.quiz_answer, payload.response)
    db.commit()
    return {"correct": delivery.quiz_correct}


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
    except Exception as e:
        print(f"[job_buddy] Handoff email failed for application {application_id}, contact {contact.id}: {e}")
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


# --- Mentorship: assigned mentor + persisted career goals that get
# folded into Job Buddy's ongoing conversation, so guidance is grounded
# in what THIS specific person said they want to work on, rather than
# starting fresh every conversation. ---

@router.get("/{application_id}/mentor", response_model=schemas.MentorAssignmentOut | None)
def get_my_mentor(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    assignment = db.query(models.MentorAssignment).filter_by(application_id=app_row.id).first()
    if not assignment:
        return None
    contact = db.query(models.OrgHumanContact).filter_by(id=assignment.contact_id).first()
    if not contact:
        return None
    return schemas.MentorAssignmentOut(
        id=assignment.id, name=contact.name, email=contact.email,
        description=contact.description, assigned_at=assignment.assigned_at,
    )


@router.get("/{application_id}/career-goals", response_model=list[schemas.CareerGoalOut])
def list_career_goals(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    return (
        db.query(models.CareerGoal).filter_by(application_id=app_row.id)
        .order_by(models.CareerGoal.created_at.desc()).all()
    )


@router.post("/{application_id}/career-goals", response_model=schemas.CareerGoalOut)
def add_career_goal(
    application_id: int,
    payload: schemas.CareerGoalCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    goal = models.CareerGoal(application_id=app_row.id, goal_text=payload.goal_text)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/{application_id}/career-goals/{goal_id}/achieve", response_model=schemas.CareerGoalOut)
def mark_goal_achieved(
    application_id: int,
    goal_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    goal = db.query(models.CareerGoal).filter_by(id=goal_id, application_id=app_row.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    goal.achieved_at = datetime.utcnow()
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{application_id}/career-goals/{goal_id}")
def delete_career_goal(
    application_id: int,
    goal_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    app_row = _get_owned_application(db, application_id, user.id)
    goal = db.query(models.CareerGoal).filter_by(id=goal_id, application_id=app_row.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    db.delete(goal)
    db.commit()
    return {"deleted": True}


# --- Onboarding checklist ---

@router.get("/{application_id}/checklist", response_model=list[schemas.ChecklistProgressItem])
def get_checklist(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Company-wide items plus (if applicable) the employee's own
    department's items, each with this employee's own completion
    status. Empty list if not org-linked -- no checklist without an
    org, same as the human-contacts endpoint."""
    app_row = _get_owned_application(db, application_id, user.id)
    if not app_row.organization_id:
        return []

    q = db.query(models.OrgChecklistItem).filter_by(organization_id=app_row.organization_id)
    if app_row.department_id:
        q = q.filter(
            (models.OrgChecklistItem.department_id == None)  # noqa: E711
            | (models.OrgChecklistItem.department_id == app_row.department_id)
        )
    else:
        q = q.filter(models.OrgChecklistItem.department_id == None)  # noqa: E711
    items = q.order_by(models.OrgChecklistItem.order).all()

    completions = {
        c.checklist_item_id: c.completed_at
        for c in db.query(models.ChecklistCompletion).filter_by(application_id=application_id).all()
    }

    return [
        schemas.ChecklistProgressItem(
            id=i.id, title=i.title, description=i.description, policy_content=i.policy_content,
            media_url=i.media_url or "", completed=i.id in completions, completed_at=completions.get(i.id),
        )
        for i in items
    ]


@router.post("/{application_id}/checklist/{item_id}/complete")
def complete_checklist_item(
    application_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Employee marks an item done themselves -- self-directed, same as
    the rest of Job Buddy. If this completes every applicable item, a
    factual notification email goes to the employee's manager (if one
    is on file), for record-keeping -- never any conversation content,
    just 'X completed their onboarding checklist.' Only fires once per
    application (manager_notified_at guards against re-firing if, say,
    an admin adds a new item after the employee already finished and
    they complete that one too)."""
    app_row = _get_owned_application(db, application_id, user.id)
    if not app_row.organization_id:
        raise HTTPException(status_code=400, detail="This job isn't linked to an organization.")

    item = db.query(models.OrgChecklistItem).filter_by(
        id=item_id, organization_id=app_row.organization_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found.")

    existing = db.query(models.ChecklistCompletion).filter_by(
        application_id=application_id, checklist_item_id=item_id
    ).first()
    if not existing:
        db.add(models.ChecklistCompletion(
            application_id=application_id, checklist_item_id=item_id,
            # Snapshot the policy text AS IT READ at the moment of
            # acknowledgment -- if the org edits the policy later, this
            # record still shows precisely what this employee agreed to,
            # independent of the live item.
            policy_content_snapshot=item.policy_content,
        ))
        db.commit()

    # Check for 100% completion across every applicable item.
    q = db.query(models.OrgChecklistItem).filter_by(organization_id=app_row.organization_id)
    if app_row.department_id:
        q = q.filter(
            (models.OrgChecklistItem.department_id == None)  # noqa: E711
            | (models.OrgChecklistItem.department_id == app_row.department_id)
        )
    else:
        q = q.filter(models.OrgChecklistItem.department_id == None)  # noqa: E711
    applicable_ids = {i.id for i in q.all()}

    completed_ids = {
        c.checklist_item_id for c in
        db.query(models.ChecklistCompletion).filter_by(application_id=application_id).all()
    }

    all_done = bool(applicable_ids) and applicable_ids.issubset(completed_ids)

    if all_done and app_row.manager_email and not app_row.manager_notified_at:
        job = app_row.job
        try:
            notifier.send_email(
                app_row.manager_email,
                f"[Riseply] {user.full_name or user.email} completed their onboarding checklist",
                (
                    f"{user.full_name or '(no name given)'} ({user.email}), {job.title} at "
                    f"{job.company}, has completed every item on their onboarding checklist.\n\n"
                    f"For your records."
                ),
            )
            app_row.manager_notified_at = datetime.utcnow()
            db.commit()
        except Exception:
            pass  # notification is best-effort -- the employee's real progress is already saved either way

    return {"completed": True, "all_done": all_done}
