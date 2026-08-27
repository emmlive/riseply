import csv
import io
import secrets
from datetime import datetime
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.config import settings
from app.security import get_current_user
from app import models, schemas

router = APIRouter(prefix="/orgs", tags=["org-buddy"])


def _validate_media_url(url: str) -> str:
    """Enforced server-side on every write, never trusting client-side
    validation alone -- rejects everything except http/https schemes,
    which blocks javascript:/data:/vbscript:/file: URI-based XSS
    attempts outright. Never fetches the URL itself (no SSRF surface);
    this only validates the string that will later be handed to the
    browser to load directly."""
    url = (url or "").strip()
    if not url:
        return ""
    if len(url) > 2000:
        raise HTTPException(status_code=400, detail="That link is too long.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Media link must start with http:// or https://")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="That doesn't look like a valid link.")
    return url


def _generate_join_code() -> str:
    return secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8].upper()


def _require_admin(db: Session, organization_id: int, user_id: int) -> models.OrganizationMember:
    """Org-wide admin only -- for company-wide actions (settings,
    billing, creating departments, managing company-wide content)."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user_id, role="admin"
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Admin access to this organization required.")
    return member


def _require_member(db: Session, organization_id: int, user_id: int) -> models.OrganizationMember:
    """Admin OR employee OR department_admin -- used for things any org
    member should be able to see, like the human contacts list (an
    employee needs to see who they can request a handoff from)."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user_id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="You're not a member of this organization.")
    return member


def _require_scope_admin(db: Session, organization_id: int, user_id: int, department_id) -> models.OrganizationMember:
    """Authorizes an action scoped to `department_id` (None = company-wide).
    An org-wide admin can act on anything. A department_admin can ONLY
    act within their own department -- they can't touch company-wide
    settings (department_id=None) or another department's content."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user_id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="You're not a member of this organization.")
    if member.role == "admin":
        return member
    if department_id is not None and member.role == "department_admin" and member.department_id == department_id:
        return member
    raise HTTPException(status_code=403, detail="You don't have admin access to this scope.")


def resolve_join_code(db: Session, code: str):
    """Returns (organization_id, department_id). Checks the org-wide
    code first, then department codes -- both live in the same
    "namespace" of unique codes, but are different tables, so this is
    a real two-step lookup, not a single query."""
    org = db.query(models.Organization).filter_by(join_code=code.upper()).first()
    if org:
        return org.id, None
    dept = db.query(models.Department).filter_by(join_code=code.upper()).first()
    if dept:
        return dept.organization_id, dept.id
    raise HTTPException(status_code=400, detail="That organization join code isn't valid.")


@router.post("", response_model=schemas.OrganizationOut)
def create_organization(
    payload: schemas.OrganizationCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Creates an org and makes the creator its admin. No approval flow
    for now -- any user can spin up an org for their company; this is
    the same self-serve pattern as the rest of Riseply's signup."""
    join_code = _generate_join_code()
    while db.query(models.Organization).filter_by(join_code=join_code).first():
        join_code = _generate_join_code()

    org = models.Organization(name=payload.name, join_code=join_code)
    db.add(org)
    db.commit()
    db.refresh(org)

    db.add(models.OrganizationMember(organization_id=org.id, user_id=user.id, role="admin"))
    db.commit()
    return org


@router.post("/sandbox", response_model=schemas.OrganizationOut)
def create_sandbox_organization(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """An admin's personal pilot org -- lets them genuinely exercise
    every Org Buddy feature (checklist, content, Culture Bot lessons,
    Ghost Onboarder) under their own account, never a real customer's.
    Admin-only, one per admin, auto-named so there's no fake company
    name to invent. Flagged is_sandbox so it's excluded from every
    place that aggregates real revenue/seat metrics across orgs."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Sandbox organizations are for admin accounts only.")

    existing = (
        db.query(models.Organization)
        .join(models.OrganizationMember, models.OrganizationMember.organization_id == models.Organization.id)
        .filter(models.OrganizationMember.user_id == user.id, models.Organization.is_sandbox.is_(True))
        .first()
    )
    if existing:
        return existing

    join_code = _generate_join_code()
    while db.query(models.Organization).filter_by(join_code=join_code).first():
        join_code = _generate_join_code()

    org = models.Organization(
        name=f"Riseply Sandbox ({user.full_name or user.email})",
        join_code=join_code, is_sandbox=True,
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    db.add(models.OrganizationMember(organization_id=org.id, user_id=user.id, role="admin"))
    db.commit()
    return org


@router.put("/{organization_id}/settings", response_model=schemas.OrganizationOut)
def update_org_settings(
    organization_id: int,
    payload: schemas.OrgSettingsUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Org-wide branding settings -- logo_url only for now. Org-wide
    admin only (not department_admin -- branding applies to the whole
    company, same scope as billing and creating departments)."""
    _require_admin(db, organization_id, user.id)
    org = db.query(models.Organization).filter_by(id=organization_id).first()

    logo_url = payload.logo_url.strip()
    if logo_url and not (logo_url.startswith("http://") or logo_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Logo URL must start with http:// or https://")

    org.logo_url = logo_url
    db.commit()
    db.refresh(org)
    return org


@router.get("/mine", response_model=list[schemas.OrganizationOut])
def my_organizations(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Orgs this user has ADMIN-LEVEL access to -- either full org-wide
    admin, or department_admin for at least one department within it.
    Both need to reach this page: an org admin manages everything, a
    department admin manages their own department's content/contacts/
    roster/checklist (already correctly scoped by the per-endpoint
    access control elsewhere in this router -- this just controls
    whether they can reach the page shell at all). Plain employees are
    correctly excluded -- they have no admin-level access anywhere, and
    everything relevant to them is already surfaced through Job Buddy."""
    rows = db.query(models.Organization).join(
        models.OrganizationMember, models.OrganizationMember.organization_id == models.Organization.id
    ).filter(
        models.OrganizationMember.user_id == user.id,
        models.OrganizationMember.role.in_(["admin", "department_admin"]),
    ).distinct().all()
    return rows


# --- Departments ---

@router.post("/{organization_id}/departments", response_model=schemas.DepartmentOut)
def create_department(
    organization_id: int,
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Org-wide admin only -- creating a department is a company-wide
    structural change, not something a department admin does to
    themselves."""
    _require_admin(db, organization_id, user.id)

    join_code = _generate_join_code()
    while (db.query(models.Organization).filter_by(join_code=join_code).first()
           or db.query(models.Department).filter_by(join_code=join_code).first()):
        join_code = _generate_join_code()

    dept = models.Department(organization_id=organization_id, name=payload.name, join_code=join_code)
    db.add(dept)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="A department with that name already exists.")
    db.refresh(dept)
    return dept


@router.get("/{organization_id}/departments", response_model=list[schemas.DepartmentOut])
def list_departments(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Org-wide admins see every department (with join codes, so they
    can distribute them). Department admins see only their own
    department. Plain employees get nothing here -- they don't need
    department join codes, only their own onboarding experience."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user.id
    ).first()
    if not member or member.role not in ("admin", "department_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    q = db.query(models.Department).filter_by(organization_id=organization_id)
    if member.role == "department_admin":
        q = q.filter_by(id=member.department_id)
    return q.all()


# --- Custom onboarding content (company-wide or department-specific) ---

@router.post("/{organization_id}/content", response_model=schemas.OrgContentOut)
def add_org_content(
    organization_id: int,
    payload: schemas.OrgContentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, payload.department_id)
    content = models.OrganizationBuddyContent(
        organization_id=organization_id, department_id=payload.department_id,
        title=payload.title, content=payload.content,
        media_url=_validate_media_url(payload.media_url),
    )
    db.add(content)
    db.commit()
    db.refresh(content)
    return content


@router.get("/{organization_id}/content", response_model=list[schemas.OrgContentOut])
def list_org_content(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Org-wide admins see everything (company-wide + every
    department's content). Department admins see company-wide content
    (read-only context for them) plus their own department's content."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user.id
    ).first()
    if not member or member.role not in ("admin", "department_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    q = db.query(models.OrganizationBuddyContent).filter_by(organization_id=organization_id)
    if member.role == "department_admin":
        q = q.filter(
            (models.OrganizationBuddyContent.department_id == None)  # noqa: E711
            | (models.OrganizationBuddyContent.department_id == member.department_id)
        )
    return q.all()


@router.delete("/{organization_id}/content/{content_id}")
def delete_org_content(
    organization_id: int,
    content_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    content = db.query(models.OrganizationBuddyContent).filter_by(
        id=content_id, organization_id=organization_id
    ).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found.")
    _require_scope_admin(db, organization_id, user.id, content.department_id)
    db.delete(content)
    db.commit()
    return {"deleted": True}


@router.get("/{organization_id}/usage", response_model=schemas.OrgUsageStats)
def org_usage_stats(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Aggregate only -- deliberately never exposes message content or
    which specific employee asked what. Same principle as the Rise
    Index: proof the tool is being used, without reading anyone's
    conversations. This is what makes it credible for employees to
    actually use it honestly."""
    _require_admin(db, organization_id, user.id)

    employees_joined = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, role="employee"
    ).count()

    app_ids = [
        row.id for row in db.query(models.Application.id).filter_by(organization_id=organization_id).all()
    ]

    plans_generated = 0
    total_messages = 0
    if app_ids:
        plans_generated = db.query(models.OnboardingPlan).filter(
            models.OnboardingPlan.application_id.in_(app_ids)
        ).count()
        total_messages = db.query(models.JobBuddyMessage).filter(
            models.JobBuddyMessage.application_id.in_(app_ids)
        ).count()

    avg = round(total_messages / employees_joined, 1) if employees_joined else 0.0

    return schemas.OrgUsageStats(
        employees_joined=employees_joined,
        plans_generated=plans_generated,
        total_messages=total_messages,
        avg_messages_per_employee=avg,
    )


@router.get("/{organization_id}/analytics", response_model=schemas.OrgAnalyticsOut)
def org_analytics(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Same aggregate-only privacy principle as org_usage_stats above --
    every section here counts/rates across employees, never singles
    one out or shows message content. Org-wide admin only (not
    department admins) since this reports across the whole
    organization, same scope as billing/settings."""
    _require_admin(db, organization_id, user.id)

    apps = db.query(models.Application).filter_by(organization_id=organization_id).all()
    app_ids = [a.id for a in apps]
    apps_by_id = {a.id: a for a in apps}

    # --- Checklist completion, per item ---
    checklist_items = db.query(models.OrgChecklistItem).filter_by(organization_id=organization_id).all()
    completions_by_item: dict[int, set[int]] = {}
    if app_ids:
        for row in db.query(models.ChecklistCompletion).filter(
            models.ChecklistCompletion.application_id.in_(app_ids)
        ).all():
            completions_by_item.setdefault(row.checklist_item_id, set()).add(row.application_id)

    checklist_stats = []
    for item in checklist_items:
        # Company-wide items apply to everyone; department-scoped items
        # only apply to that department's employees -- same layering
        # rule used everywhere else (content, lessons, contacts).
        assigned = [a for a in apps if item.department_id is None or a.department_id == item.department_id]
        completed_ids = completions_by_item.get(item.id, set())
        completed = len([a for a in assigned if a.id in completed_ids])
        total = len(assigned)
        checklist_stats.append(schemas.ChecklistItemStats(
            item_id=item.id, title=item.title, total_assigned=total, total_completed=completed,
            completion_rate=round(completed / total * 100, 1) if total else 0.0,
        ))

    # --- Lesson quiz performance -- only lessons that actually have a quiz ---
    lessons = db.query(models.OrgLesson).filter(
        models.OrgLesson.organization_id == organization_id,
        models.OrgLesson.quiz_question != "",
    ).all()
    deliveries_by_lesson: dict[int, list] = {}
    if app_ids:
        for row in db.query(models.LessonDelivery).filter(
            models.LessonDelivery.application_id.in_(app_ids),
            models.LessonDelivery.quiz_response.isnot(None),
        ).all():
            deliveries_by_lesson.setdefault(row.lesson_id, []).append(row)

    lesson_stats = []
    for lesson in lessons:
        attempts = deliveries_by_lesson.get(lesson.id, [])
        if not attempts:
            continue  # no signal yet -- omit rather than show a misleading 0%
        correct = len([d for d in attempts if d.quiz_correct])
        lesson_stats.append(schemas.LessonQuizStats(
            lesson_id=lesson.id, title=lesson.title, quiz_question=lesson.quiz_question,
            total_attempts=len(attempts), correct_count=correct,
            correct_rate=round(correct / len(attempts) * 100, 1),
        ))

    # --- Ghost Onboarder gaps -- unmatched questions, grouped by exact
    # text (a simple, honest approximation -- no NLP clustering that
    # could group genuinely different questions together and mislead) ---
    qa_gap_counts: dict[str, int] = {}
    for row in db.query(models.OrgQALog.question).filter_by(
        organization_id=organization_id, matched_content=False
    ).all():
        q = row.question.strip()
        if q:
            qa_gap_counts[q] = qa_gap_counts.get(q, 0) + 1
    qa_gaps = sorted(
        [schemas.QAGapStats(question=q, count=c) for q, c in qa_gap_counts.items()],
        key=lambda x: x.count, reverse=True,
    )[:20]

    # --- Per-department completion + time-to-complete-onboarding ---
    # An employee counts as "fully onboarded" once they've completed
    # every checklist item that actually applies to their scope
    # (company-wide + their own department's, if any) -- not just
    # "some items done", and not requiring department-scoped items
    # from OTHER departments they don't belong to.
    items_by_dept: dict = {}
    companywide_items = [i.id for i in checklist_items if i.department_id is None]
    for item in checklist_items:
        if item.department_id is not None:
            items_by_dept.setdefault(item.department_id, []).append(item.id)

    completed_items_by_app: dict[int, set[int]] = {}
    for item_id, app_id_set in completions_by_item.items():
        for aid in app_id_set:
            completed_items_by_app.setdefault(aid, set()).add(item_id)

    completion_dates_by_app: dict = {}
    if app_ids:
        for row in db.query(models.ChecklistCompletion).filter(
            models.ChecklistCompletion.application_id.in_(app_ids)
        ).all():
            existing = completion_dates_by_app.get(row.application_id)
            if existing is None or row.completed_at > existing:
                completion_dates_by_app[row.application_id] = row.completed_at

    days_to_complete: list[float] = []
    dept_buckets: dict = {}  # department_id (or None) -> {"total": n, "completed": n}
    for app in apps:
        applicable = set(companywide_items) | set(items_by_dept.get(app.department_id, []))
        completed_set = completed_items_by_app.get(app.id, set())
        fully_onboarded = bool(applicable) and applicable.issubset(completed_set)

        bucket = dept_buckets.setdefault(app.department_id, {"total": 0, "completed": 0})
        bucket["total"] += 1
        if fully_onboarded:
            bucket["completed"] += 1
            finished_at = completion_dates_by_app.get(app.id)
            if finished_at:
                days_to_complete.append((finished_at - app.created_at).total_seconds() / 86400)

    dept_names = {d.id: d.name for d in db.query(models.Department).filter_by(organization_id=organization_id).all()}
    department_stats = []
    for dept_id, bucket in dept_buckets.items():
        department_stats.append(schemas.DepartmentStats(
            department_id=dept_id,
            department_name=dept_names.get(dept_id, "Company-wide") if dept_id else "Company-wide",
            total_employees=bucket["total"], completed_onboarding=bucket["completed"],
            completion_rate=round(bucket["completed"] / bucket["total"] * 100, 1) if bucket["total"] else 0.0,
        ))

    # --- Mentorship program health ---
    # Aggregate-only: counts and an average rating, never which
    # employee said what -- same boundary as every other section here.
    assignments = db.query(models.MentorAssignment).filter(
        models.MentorAssignment.application_id.in_(app_ids)
    ).all() if app_ids else []
    assignment_ids = [a.id for a in assignments]
    meetings = db.query(models.MentorMeetingLog).filter(
        models.MentorMeetingLog.mentor_assignment_id.in_(assignment_ids)
    ).all() if assignment_ids else []
    ratings = [m.rating for m in meetings if m.rating is not None]

    mentorship_stats = schemas.MentorshipStats(
        total_pairings=len(assignments),
        employees_with_mentor_pct=round(len(assignments) / len(apps) * 100, 1) if apps else 0.0,
        total_meetings_logged=len(meetings),
        avg_meetings_per_pairing=round(len(meetings) / len(assignments), 1) if assignments else 0.0,
        avg_feedback_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
    )

    return schemas.OrgAnalyticsOut(
        total_employees=len(apps),
        avg_days_to_complete_onboarding=round(sum(days_to_complete) / len(days_to_complete), 1) if days_to_complete else None,
        checklist_items=checklist_stats,
        lesson_quizzes=lesson_stats,
        qa_gaps=qa_gaps,
        departments=department_stats,
        mentorship=mentorship_stats,
    )


@router.get("/{organization_id}/analytics/export.csv")
def org_analytics_csv(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Same data as GET .../analytics, as a downloadable CSV -- for
    putting an actual report in front of leadership rather than
    screenshotting the dashboard."""
    _require_admin(db, organization_id, user.id)
    analytics = org_analytics(organization_id, db, user)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Riseply Org Buddy Analytics"])
    writer.writerow(["Total employees", analytics.total_employees])
    writer.writerow(["Avg days to complete onboarding",
                      analytics.avg_days_to_complete_onboarding if analytics.avg_days_to_complete_onboarding is not None else "N/A"])
    writer.writerow([])

    writer.writerow(["Checklist item", "Assigned", "Completed", "Completion rate %"])
    for s in analytics.checklist_items:
        writer.writerow([s.title, s.total_assigned, s.total_completed, s.completion_rate])
    writer.writerow([])

    writer.writerow(["Lesson quiz", "Question", "Attempts", "Correct", "Correct rate %"])
    for s in analytics.lesson_quizzes:
        writer.writerow([s.title, s.quiz_question, s.total_attempts, s.correct_count, s.correct_rate])
    writer.writerow([])

    writer.writerow(["Department", "Employees", "Completed onboarding", "Completion rate %"])
    for s in analytics.departments:
        writer.writerow([s.department_name, s.total_employees, s.completed_onboarding, s.completion_rate])
    writer.writerow([])

    writer.writerow(["Unanswered question (Ghost Onboarder gap)", "Times asked"])
    for s in analytics.qa_gaps:
        writer.writerow([s.question, s.count])
    writer.writerow([])

    m = analytics.mentorship
    writer.writerow(["Mentorship program"])
    writer.writerow(["Total pairings", m.total_pairings])
    writer.writerow(["Employees with a mentor assigned (%)", m.employees_with_mentor_pct])
    writer.writerow(["Total meetings logged", m.total_meetings_logged])
    writer.writerow(["Avg meetings per pairing", m.avg_meetings_per_pairing])
    writer.writerow(["Avg feedback rating (1-5)", m.avg_feedback_rating if m.avg_feedback_rating is not None else "N/A"])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="riseply_org_{organization_id}_analytics.csv"'},
    )


# --- CSV roster upload -- pre-register expected employees so they don't
# have to hand-type their own title/tenure when they join ---

MAX_ROSTER_UPLOAD_BYTES = 2 * 1024 * 1024  # 2MB is generous for a CSV roster


@router.post("/{organization_id}/roster/upload", response_model=schemas.OrgRosterUploadResult)
async def upload_roster(
    organization_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Expects a CSV with headers: email, title, tenure, department,
    manager_email (all but email optional). department is matched by
    NAME against this org's existing departments -- an unrecognized
    name is reported as an error for that row rather than silently
    dropped, so a typo doesn't quietly leave someone without their
    department's content. manager_email is used only to send a factual
    completion notification when the employee's checklist hits 100% --
    never any conversation content."""
    _require_admin(db, organization_id, user.id)

    contents = await file.read()
    if len(contents) > MAX_ROSTER_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large — please keep it under 2MB.")

    try:
        text = contents.decode("utf-8-sig")  # handles Excel's BOM-prefixed UTF-8 exports
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Couldn't read that file as text — please upload a plain CSV.")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "email" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status_code=400, detail="CSV must have an 'email' column (title, tenure, department, manager_email optional).")

    valid_tenures = {"just_started", "a_few_months", "well_established"}
    dept_by_name = {
        d.name.strip().lower(): d.id
        for d in db.query(models.Department).filter_by(organization_id=organization_id).all()
    }
    added, updated, errors = 0, 0, []

    for i, row in enumerate(reader, start=2):  # start=2: row 1 is the header
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
        email = row.get("email", "")
        if not email or "@" not in email:
            errors.append(f"Row {i}: missing or invalid email, skipped.")
            continue

        tenure = row.get("tenure", "") or "just_started"
        if tenure not in valid_tenures:
            errors.append(f"Row {i}: unrecognized tenure '{tenure}', defaulted to just_started.")
            tenure = "just_started"

        department_id = None
        dept_name = row.get("department", "")
        if dept_name:
            department_id = dept_by_name.get(dept_name.lower())
            if department_id is None:
                errors.append(f"Row {i}: unrecognized department '{dept_name}', left as company-wide.")

        manager_email = row.get("manager_email", "")

        existing = db.query(models.OrgRosterEntry).filter_by(
            organization_id=organization_id, email=email
        ).first()
        if existing:
            existing.title = row.get("title", existing.title)
            existing.tenure = tenure
            existing.department_id = department_id if dept_name else existing.department_id
            existing.manager_email = manager_email or existing.manager_email
            updated += 1
        else:
            db.add(models.OrgRosterEntry(
                organization_id=organization_id, email=email,
                title=row.get("title", ""), tenure=tenure, department_id=department_id,
                manager_email=manager_email,
            ))
            added += 1

    db.commit()
    return schemas.OrgRosterUploadResult(added=added, updated=updated, errors=errors)


@router.get("/{organization_id}/roster", response_model=list[schemas.OrgRosterEntryOut])
def list_roster(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Enrollment status only (has this person joined yet) -- never
    conversation content. Department admins see only their own
    department's roster entries."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user.id
    ).first()
    if not member or member.role not in ("admin", "department_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    q = db.query(models.OrgRosterEntry).filter_by(organization_id=organization_id)
    if member.role == "department_admin":
        q = q.filter_by(department_id=member.department_id)
    rows = q.all()
    return [
        schemas.OrgRosterEntryOut(
            id=r.id, email=r.email, title=r.title, tenure=r.tenure,
            department_id=r.department_id, manager_email=r.manager_email,
            joined=r.matched_user_id is not None,
            created_at=r.created_at,
        )
        for r in rows
    ]


# --- Human contacts (for handoffs -- things AI structurally can't do) ---

@router.post("/{organization_id}/contacts", response_model=schemas.OrgContactOut)
def add_contact(
    organization_id: int,
    payload: schemas.OrgContactCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, payload.department_id)
    contact = models.OrgHumanContact(
        organization_id=organization_id, department_id=payload.department_id,
        name=payload.name, email=payload.email, description=payload.description,
        is_mentor=payload.is_mentor, mentor_bio=payload.mentor_bio,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/{organization_id}/contacts", response_model=list[schemas.OrgContactOut])
def list_contacts(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Any org member can see this -- an employee needs to know who's
    available before they can request a handoff to them. A plain
    employee sees company-wide contacts plus their own department's;
    admins/department_admins see the same scope they can manage."""
    member = _require_member(db, organization_id, user.id)
    q = db.query(models.OrgHumanContact).filter_by(organization_id=organization_id)
    if member.role != "admin":
        dept_id = member.department_id
        q = q.filter(
            (models.OrgHumanContact.department_id == None)  # noqa: E711
            | (models.OrgHumanContact.department_id == dept_id)
        )
    return q.all()


@router.delete("/{organization_id}/contacts/{contact_id}")
def delete_contact(
    organization_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    contact = db.query(models.OrgHumanContact).filter_by(id=contact_id, organization_id=organization_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")
    _require_scope_admin(db, organization_id, user.id, contact.department_id)
    db.delete(contact)
    db.commit()
    return {"deleted": True}


# --- Mentor assignment -- pairs an employee with one specific mentor
# from the contact pool (a contact with is_mentor=True), rather than
# just leaving them in the general list anyone can reach out to. ---

@router.get("/{organization_id}/employees", response_model=list[schemas.OrgEmployeeOut])
def list_employees(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Joined employees (not the pre-registration roster -- this is who's
    actually signed up), with enough detail to assign a mentor to each.
    Deliberately only name/email/department/join date/mentor status --
    same aggregate-adjacent, no-conversation-content boundary as
    everywhere else admin-facing in Org Buddy."""
    _require_admin(db, organization_id, user.id)

    rows = (
        db.query(models.Application, models.User)
        .join(models.User, models.Application.user_id == models.User.id)
        .filter(models.Application.organization_id == organization_id)
        .order_by(models.Application.created_at.desc())
        .all()
    )

    dept_names = {d.id: d.name for d in db.query(models.Department).filter_by(organization_id=organization_id).all()}

    app_ids = [a.id for a, _ in rows]
    mentor_names: dict[int, str] = {}
    mentor_assignment_ids: dict[int, int] = {}
    if app_ids:
        assignments = db.query(models.MentorAssignment).filter(models.MentorAssignment.application_id.in_(app_ids)).all()
        contact_ids = [a.contact_id for a in assignments]
        contacts_by_id = {c.id: c.name for c in db.query(models.OrgHumanContact).filter(models.OrgHumanContact.id.in_(contact_ids)).all()} if contact_ids else {}
        for a in assignments:
            mentor_names[a.application_id] = contacts_by_id.get(a.contact_id)
            mentor_assignment_ids[a.application_id] = a.id

    return [
        schemas.OrgEmployeeOut(
            application_id=app_row.id, user_email=user_row.email,
            user_full_name=user_row.full_name or user_row.email,
            department_id=app_row.department_id,
            department_name=dept_names.get(app_row.department_id) if app_row.department_id else None,
            joined_at=app_row.created_at,
            mentor_name=mentor_names.get(app_row.id),
            mentor_assignment_id=mentor_assignment_ids.get(app_row.id),
        )
        for app_row, user_row in rows
    ]


@router.get("/{organization_id}/mentors", response_model=list[schemas.OrgContactOut])
def list_mentors(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The assignable mentor pool -- admin-facing (for picking who to
    assign), scoped the same way as the general contact list."""
    member = _require_member(db, organization_id, user.id)
    q = db.query(models.OrgHumanContact).filter_by(organization_id=organization_id, is_mentor=True)
    if member.role != "admin":
        dept_id = member.department_id
        q = q.filter(
            (models.OrgHumanContact.department_id == None)  # noqa: E711
            | (models.OrgHumanContact.department_id == dept_id)
        )
    return q.all()


@router.post("/{organization_id}/employees/{application_id}/assign-mentor", response_model=schemas.MentorAssignmentOut)
def assign_mentor(
    organization_id: int,
    application_id: int,
    payload: schemas.MentorAssignRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    application = db.query(models.Application).filter_by(
        id=application_id, organization_id=organization_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Employee not found in this organization.")

    contact = db.query(models.OrgHumanContact).filter_by(
        id=payload.contact_id, organization_id=organization_id, is_mentor=True
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="That mentor wasn't found.")

    _require_scope_admin(db, organization_id, user.id, application.department_id)

    existing = db.query(models.MentorAssignment).filter_by(application_id=application_id).first()
    if existing:
        existing.contact_id = contact.id
        existing.assigned_at = datetime.utcnow()
        assignment = existing
    else:
        assignment = models.MentorAssignment(application_id=application_id, contact_id=contact.id)
        db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return schemas.MentorAssignmentOut(
        id=assignment.id, contact_id=contact.id, name=contact.name, email=contact.email,
        description=contact.description, assigned_at=assignment.assigned_at,
    )


@router.get("/{organization_id}/employees/{application_id}/suggested-mentors", response_model=list[schemas.SuggestedMentorOut])
def suggested_mentors(
    organization_id: int,
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """AI-assisted ranking of the mentor pool for one specific employee,
    scored against their resume + stated career goals. Advisory only --
    assign_mentor above is completely unchanged and still requires an
    admin to actually pick someone; this just gives them a
    data-informed starting point instead of a bare list of names.

    Computed on demand rather than in a background batch: the mentor
    pool for a single org is small (a handful to a few dozen people,
    not thousands of job postings), so a few sequential Claude calls
    here comfortably finish within a normal request/response cycle --
    unlike the job-matching pipeline, this doesn't need the
    background-task treatment that scheduled-run required."""
    application = db.query(models.Application).filter_by(
        id=application_id, organization_id=organization_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Employee not found in this organization.")

    _require_scope_admin(db, organization_id, user.id, application.department_id)

    employee = db.query(models.User).filter_by(id=application.user_id).first()
    goal_rows = (
        db.query(models.CareerGoal)
        .filter_by(application_id=application_id, achieved_at=None)
        .order_by(models.CareerGoal.created_at.desc())
        .all()
    )
    goal_text = goal_rows[0].goal_text if goal_rows else ""

    mentors = db.query(models.OrgHumanContact).filter_by(
        organization_id=organization_id, is_mentor=True
    ).all()
    if not mentors:
        return []

    from app.services import mentor_matcher
    ranked = mentor_matcher.suggest_mentors(employee.resume_text or "", goal_text, mentors)
    return [schemas.SuggestedMentorOut(**r) for r in ranked]


# --- Mentor meeting logs (participation record + optional employee feedback) ---

def _require_mentor_pairing_access(db: Session, organization_id: int, user_id: int, assignment: models.MentorAssignment):
    """Either the org admin overseeing the pairing's department, the
    employee themselves, or the assigned mentor may log/view meetings
    for a pairing -- narrower than the general admin-only pattern most
    of this file uses, since the two participants in the pairing need
    to be able to log their own meetings without needing admin rights."""
    application = db.query(models.Application).filter_by(id=assignment.application_id).first()
    if application and application.user_id == user_id:
        return  # the employee themselves
    contact = db.query(models.OrgHumanContact).filter_by(id=assignment.contact_id).first()
    if contact:
        mentor_user = db.query(models.User).filter_by(email=contact.email).first()
        if mentor_user and mentor_user.id == user_id:
            return  # the assigned mentor
    _require_scope_admin(db, organization_id, user_id, application.department_id if application else None)


@router.post("/{organization_id}/mentor-assignments/{assignment_id}/meetings", response_model=schemas.MentorMeetingLogOut)
def log_mentor_meeting(
    organization_id: int,
    assignment_id: int,
    payload: schemas.MentorMeetingLogCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    _require_mentor_pairing_access(db, organization_id, user.id, assignment)

    log = models.MentorMeetingLog(
        mentor_assignment_id=assignment_id, logged_by_user_id=user.id,
        meeting_date=payload.meeting_date, notes=payload.notes,
    )
    db.add(log)
    # A logged meeting is a live signal the pairing is active -- resets
    # the reminder guard the same way any check-in resets a "we haven't
    # heard from you" nudge, so mentor_reminders.py doesn't nag a pair
    # that just met.
    assignment.reminder_last_sent_at = None
    db.commit()
    db.refresh(log)
    return log


@router.get("/{organization_id}/mentor-assignments/{assignment_id}/meetings", response_model=list[schemas.MentorMeetingLogOut])
def list_mentor_meetings(
    organization_id: int,
    assignment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    _require_mentor_pairing_access(db, organization_id, user.id, assignment)

    return (
        db.query(models.MentorMeetingLog)
        .filter_by(mentor_assignment_id=assignment_id)
        .order_by(models.MentorMeetingLog.meeting_date.desc())
        .all()
    )


@router.post("/{organization_id}/mentor-meetings/{meeting_id}/feedback", response_model=schemas.MentorMeetingLogOut)
def submit_meeting_feedback(
    organization_id: int,
    meeting_id: int,
    payload: schemas.MentorMeetingFeedbackCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Employee-only (not the mentor, not the admin) -- feedback on a
    meeting is the employee's own assessment of how it went for them,
    same as how CareerGoal is employee-owned."""
    meeting = db.query(models.MentorMeetingLog).join(
        models.MentorAssignment, models.MentorMeetingLog.mentor_assignment_id == models.MentorAssignment.id
    ).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorMeetingLog.id == meeting_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    application = db.query(models.Application).join(
        models.MentorAssignment, models.MentorAssignment.application_id == models.Application.id
    ).filter(models.MentorAssignment.id == meeting.mentor_assignment_id).first()
    if not application or application.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the employee in this pairing can submit feedback on their own meeting.")

    meeting.rating = payload.rating
    meeting.feedback_note = payload.feedback_note
    db.commit()
    db.refresh(meeting)
    return meeting


# --- Onboarding checklist (company-wide or department-specific templates) ---

@router.post("/{organization_id}/checklist", response_model=schemas.ChecklistItemOut)
def add_checklist_item(
    organization_id: int,
    payload: schemas.ChecklistItemCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, payload.department_id)
    item = models.OrgChecklistItem(
        organization_id=organization_id, department_id=payload.department_id,
        title=payload.title, description=payload.description,
        policy_content=payload.policy_content, order=payload.order,
        media_url=_validate_media_url(payload.media_url),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{organization_id}/checklist", response_model=list[schemas.ChecklistItemOut])
def list_checklist_items(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin/department_admin management view -- same scoping rule as
    content and contacts: department admins see company-wide (context)
    plus their own department's items."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user.id
    ).first()
    if not member or member.role not in ("admin", "department_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    q = db.query(models.OrgChecklistItem).filter_by(organization_id=organization_id)
    if member.role == "department_admin":
        q = q.filter(
            (models.OrgChecklistItem.department_id == None)  # noqa: E711
            | (models.OrgChecklistItem.department_id == member.department_id)
        )
    return q.order_by(models.OrgChecklistItem.order).all()


@router.delete("/{organization_id}/checklist/{item_id}")
def delete_checklist_item(
    organization_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    item = db.query(models.OrgChecklistItem).filter_by(id=item_id, organization_id=organization_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found.")
    _require_scope_admin(db, organization_id, user.id, item.department_id)
    db.delete(item)
    db.commit()
    return {"deleted": True}


@router.get("/{organization_id}/checklist/{item_id}/acknowledgments", response_model=list[schemas.PolicyAcknowledgment])
def list_acknowledgments(
    organization_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Compliance record for a specific policy item -- who acknowledged
    it and when. Deliberately returns only email/name/timestamp, never
    the acknowledged text itself here (that's available per-completion
    if ever needed, but this list view is for headcount/status, not a
    document viewer) and never anything about Job Buddy conversations.
    Same administrative-data category as roster 'joined' status."""
    item = db.query(models.OrgChecklistItem).filter_by(id=item_id, organization_id=organization_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found.")
    _require_scope_admin(db, organization_id, user.id, item.department_id)

    rows = (
        db.query(models.ChecklistCompletion, models.Application, models.User)
        .join(models.Application, models.ChecklistCompletion.application_id == models.Application.id)
        .join(models.User, models.Application.user_id == models.User.id)
        .filter(models.ChecklistCompletion.checklist_item_id == item_id)
        .all()
    )
    return [
        schemas.PolicyAcknowledgment(
            application_id=app_row.id, employee_email=user_row.email,
            employee_name=user_row.full_name or "", completed_at=completion.completed_at,
        )
        for completion, app_row, user_row in rows
    ]


# --- Billing: hybrid (base plan subscription + seat overage) ---

def _stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing isn't configured yet.")
    import stripe
    stripe.api_key = settings.stripe_secret_key
    return stripe


@router.post("/{organization_id}/subscribe")
def subscribe_org(
    organization_id: int,
    plan: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if plan not in ("starter", "growth"):
        raise HTTPException(status_code=400, detail="Plan must be 'starter' or 'growth' (contact us for Enterprise).")

    org = _require_admin(db, organization_id, user.id)
    org_row = db.query(models.Organization).filter_by(id=organization_id).first()

    if org_row.is_sandbox:
        raise HTTPException(status_code=400, detail="Sandbox organizations can't be billed — this one is for internal testing only.")

    price_id = settings.stripe_price_id_org_starter if plan == "starter" else settings.stripe_price_id_org_growth
    if not price_id:
        raise HTTPException(status_code=503, detail=f"The {plan} plan isn't configured yet — its Stripe Price ID is unset.")

    stripe = _stripe()
    if not org_row.stripe_customer_id:
        customer = stripe.Customer.create(name=org_row.name)
        org_row.stripe_customer_id = customer.id
        db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=org_row.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        metadata={"organization_id": str(organization_id), "plan": plan},
    )
    return {"checkout_url": session.url}


@router.get("/{organization_id}/billing", response_model=schemas.OrgBillingOut)
def org_billing(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Overage is calculated and shown here, but NOT automatically
    invoiced yet -- that needs Stripe metered/usage-based billing, which
    is real additional infrastructure beyond this flat-subscription
    pattern (see README). For now this is visibility, not automated
    billing -- an org that's over their seat count sees it clearly, and
    reconciling that today is a manual step, not a hidden one."""
    _require_admin(db, organization_id, user.id)
    org_row = db.query(models.Organization).filter_by(id=organization_id).first()

    employees_joined = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, role="employee"
    ).count()

    overage_seats = max(0, employees_joined - org_row.included_seats)
    overage_cost = round(overage_seats * settings.org_plan_overage_price_per_seat_usd, 2)

    return schemas.OrgBillingOut(
        plan=org_row.plan or "none",
        subscription_status=org_row.subscription_status or "inactive",
        included_seats=org_row.included_seats,
        employees_joined=employees_joined,
        overage_seats=overage_seats,
        overage_cost_usd=overage_cost,
    )


@router.post("/{organization_id}/request-enterprise-billing", response_model=schemas.EnterpriseBillingRequestOut)
def request_enterprise_billing(
    organization_id: int,
    payload: schemas.EnterpriseBillingRequestCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Deliberately just captures the request and notifies a human --
    see the note on EnterpriseBillingRequest for why this isn't an
    automated invoicing system."""
    _require_admin(db, organization_id, user.id)
    org_row = db.query(models.Organization).filter_by(id=organization_id).first()

    request = models.EnterpriseBillingRequest(
        organization_id=organization_id, requested_by_user_id=user.id,
        billing_contact_name=payload.billing_contact_name,
        billing_contact_email=payload.billing_contact_email,
        estimated_employees=payload.estimated_employees, notes=payload.notes,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    support_inbox = settings.support_email or settings.resend_from_email
    try:
        from app.services import notifier
        notifier.send_email(
            support_inbox,
            f"[Riseply] Enterprise billing request — {org_row.name}",
            (
                f"Organization: {org_row.name} (id {organization_id})\n"
                f"Requested by: {user.full_name or user.email} ({user.email})\n"
                f"Billing contact: {payload.billing_contact_name} <{payload.billing_contact_email}>\n"
                f"Estimated employees: {payload.estimated_employees}\n\n"
                f"Notes:\n{payload.notes or '(none)'}"
            ),
        )
    except Exception as e:
        print(f"[org_buddy] Enterprise billing request notification failed for org {organization_id}: {e}")
        # Deliberately not raised as an error -- the request is already
        # saved and admin-visible either way; a failed notification
        # email shouldn't make the person think their request was lost.

    return request


@router.get("/{organization_id}/enterprise-billing-requests", response_model=list[schemas.EnterpriseBillingRequestOut])
def list_enterprise_billing_requests(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_admin(db, organization_id, user.id)
    return (
        db.query(models.EnterpriseBillingRequest).filter_by(organization_id=organization_id)
        .order_by(models.EnterpriseBillingRequest.created_at.desc()).all()
    )


@router.get("/{organization_id}/sso-config", response_model=schemas.OrgSSOConfigOut | None)
def get_sso_config(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_admin(db, organization_id, user.id)
    return db.query(models.OrgSSOConfig).filter_by(organization_id=organization_id).first()


@router.post("/{organization_id}/sso-config", response_model=schemas.OrgSSOConfigOut)
def set_sso_config(
    organization_id: int,
    payload: schemas.OrgSSOConfigCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Validates the issuer actually resolves to a real OIDC discovery
    document before saving -- catches a typo'd issuer URL immediately
    at setup time, rather than only surfacing as a broken login for
    the first employee who tries to use it."""
    _require_admin(db, organization_id, user.id)

    from app.services import oidc_sso
    discovery = oidc_sso.discover(payload.issuer)
    if not discovery.get("authorization_endpoint") or not discovery.get("token_endpoint") or not discovery.get("jwks_uri"):
        raise HTTPException(status_code=400, detail="That issuer's discovery document is missing required endpoints — double check the issuer URL.")

    config = db.query(models.OrgSSOConfig).filter_by(organization_id=organization_id).first()
    if config:
        config.provider_name = payload.provider_name
        config.issuer = payload.issuer
        config.client_id = payload.client_id
        config.client_secret = payload.client_secret
        config.allowed_email_domain = payload.allowed_email_domain
        config.enabled = True
    else:
        config = models.OrgSSOConfig(
            organization_id=organization_id, provider_name=payload.provider_name,
            issuer=payload.issuer, client_id=payload.client_id, client_secret=payload.client_secret,
            allowed_email_domain=payload.allowed_email_domain,
        )
        db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.delete("/{organization_id}/sso-config")
def delete_sso_config(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_admin(db, organization_id, user.id)
    config = db.query(models.OrgSSOConfig).filter_by(organization_id=organization_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="No SSO configuration to remove.")
    db.delete(config)
    db.commit()
    return {"deleted": True}


# --- Ghost Onboarder: what employees have been asking ---

@router.get("/{organization_id}/qa-logs", response_model=list[schemas.OrgQALogOut])
def list_qa_logs(
    organization_id: int,
    unmatched_only: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin-visible log of instant Q&A exchanges -- the direct signal
    for what to add to uploaded content. unmatched_only surfaces
    questions nothing in the org's content covered yet, which is the
    highest-value view: it's literally a list of content gaps."""
    _require_admin(db, organization_id, user.id)
    q = db.query(models.OrgQALog, models.User.email).join(
        models.User, models.OrgQALog.user_id == models.User.id
    ).filter(models.OrgQALog.organization_id == organization_id)
    if unmatched_only:
        q = q.filter(models.OrgQALog.matched_content.is_(False))
    q = q.order_by(models.OrgQALog.created_at.desc()).limit(200)

    return [
        schemas.OrgQALogOut(
            id=log.id, application_id=log.application_id, user_email=email,
            question=log.question, answer=log.answer, matched_content=log.matched_content,
            created_at=log.created_at,
        )
        for log, email in q.all()
    ]


# --- Culture Bot: admin-authored lesson templates ---

@router.post("/{organization_id}/lessons", response_model=schemas.OrgLessonOut)
def add_lesson(
    organization_id: int,
    payload: schemas.OrgLessonCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, payload.department_id)
    lesson = models.OrgLesson(
        organization_id=organization_id, department_id=payload.department_id,
        day_offset=payload.day_offset, title=payload.title, content=payload.content,
        quiz_question=payload.quiz_question, quiz_answer=payload.quiz_answer, order=payload.order,
        media_url=_validate_media_url(payload.media_url),
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.get("/{organization_id}/lessons", response_model=list[schemas.OrgLessonOut])
def list_lessons(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin/department_admin management view -- same scoping as the
    checklist management view: department admins see company-wide
    (context) plus their own department's lessons."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user.id
    ).first()
    if not member or member.role not in ("admin", "department_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    q = db.query(models.OrgLesson).filter_by(organization_id=organization_id)
    if member.role == "department_admin":
        q = q.filter(
            (models.OrgLesson.department_id == None)  # noqa: E711
            | (models.OrgLesson.department_id == member.department_id)
        )
    return q.order_by(models.OrgLesson.day_offset, models.OrgLesson.order).all()


@router.delete("/{organization_id}/lessons/{lesson_id}")
def delete_lesson(
    organization_id: int,
    lesson_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    lesson = db.query(models.OrgLesson).filter_by(id=lesson_id, organization_id=organization_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    _require_scope_admin(db, organization_id, user.id, lesson.department_id)
    db.delete(lesson)
    db.commit()
    return {"deleted": True}


# --- Culture Bot: daily delivery run -- see /internal/culture-bot-run
# in internal.py for the actual scheduled-trigger endpoint (same
# CRON_SECRET + GitHub Actions pattern as scheduled matching, kept
# together with that endpoint rather than duplicated here).
