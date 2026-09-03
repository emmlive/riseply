import csv
import io
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.config import settings
from app.security import get_current_user
from app import models, schemas
from app.services import calendar_oauth
from app.services import mentorship_relationships
from app.services import internal_jobs
from app.services import certifications

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
    """Org-wide branding and workflow settings. Org-wide admin only
    (not department_admin -- these apply to the whole company, same
    scope as billing and creating departments). A partial update:
    logo_url is always set from whatever's sent (empty string clears
    it, matching existing behavior), but
    require_manager_approval_for_internal_jobs only changes when
    explicitly included -- see OrgSettingsUpdate's own docstring for
    why that one specifically needs None-means-leave-alone semantics."""
    _require_admin(db, organization_id, user.id)
    org = db.query(models.Organization).filter_by(id=organization_id).first()

    logo_url = payload.logo_url.strip()
    if logo_url and not (logo_url.startswith("http://") or logo_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Logo URL must start with http:// or https://")

    org.logo_url = logo_url
    if payload.require_manager_approval_for_internal_jobs is not None:
        org.require_manager_approval_for_internal_jobs = payload.require_manager_approval_for_internal_jobs
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

# Deliberately a small, fixed set rather than free text -- keeps
# filtering/display consistent and avoids "Wellbeing", "wellbeing",
# "Well-being" all existing as different categories in the same org.
# "General" is the default for content that isn't any of the more
# specific ones, not a value an admin has to explicitly choose.
CONTENT_CATEGORIES = ["General", "Policy", "Training Guide", "Mentoring Resource", "Wellbeing"]


def _validate_category(category: str) -> str:
    if category not in CONTENT_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of: {', '.join(CONTENT_CATEGORIES)}")
    return category


@router.get("/content/categories")
def get_content_categories():
    """Static list, but served from the API rather than hardcoded
    separately in the frontend -- one source of truth for what's
    valid, so adding a category later doesn't require remembering to
    update it in two places."""
    return CONTENT_CATEGORIES


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
        category=_validate_category(payload.category),
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

    pairings_ended = sum(1 for a in assignments if a.ended_at is not None)
    retrospectives = db.query(models.MentorRetrospective).filter(
        models.MentorRetrospective.mentor_assignment_id.in_(assignment_ids)
    ).all() if assignment_ids else []
    recommend_answers = [r.would_recommend_mentor for r in retrospectives if r.would_recommend_mentor is not None]

    # Group/reciprocal relationships are organization_id-scoped directly
    # (unlike MentorAssignment, reached via app_ids) -- see
    # MentorshipRelationship's own docstring for why they're a
    # genuinely separate system from 1:1 pairings.
    relationships = db.query(models.MentorshipRelationship).filter_by(organization_id=organization_id).all()
    total_group_relationships = sum(1 for r in relationships if r.relationship_type == "group")
    total_reciprocal_relationships = sum(1 for r in relationships if r.relationship_type == "reciprocal")
    relationship_ids = [r.id for r in relationships]
    total_relationship_meetings_logged = db.query(models.MentorshipMeetingLog).filter(
        models.MentorshipMeetingLog.relationship_id.in_(relationship_ids)
    ).count() if relationship_ids else 0

    mentorship_stats = schemas.MentorshipStats(
        total_pairings=len(assignments),
        employees_with_mentor_pct=round(len(assignments) / len(apps) * 100, 1) if apps else 0.0,
        total_meetings_logged=len(meetings),
        avg_meetings_per_pairing=round(len(meetings) / len(assignments), 1) if assignments else 0.0,
        avg_feedback_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
        pairings_ended=pairings_ended,
        would_recommend_mentor_pct=round(sum(recommend_answers) / len(recommend_answers) * 100, 1) if recommend_answers else None,
        total_group_relationships=total_group_relationships,
        total_reciprocal_relationships=total_reciprocal_relationships,
        total_relationship_meetings_logged=total_relationship_meetings_logged,
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


@router.get("/{organization_id}/analytics/trends", response_model=schemas.OrgAnalyticsTrends)
def get_org_analytics_trends(
    organization_id: int,
    months: int = 6,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Month-over-month activity counts -- computed from existing
    timestamped rows (Application.created_at, ChecklistCompletion.
    completed_at, MentorMeetingLog.created_at,
    EmployeeCertification.completed_at), not a separate stored
    snapshot table. Bucketed in Python rather than SQL (strftime/
    date_trunc), matching the same month-string pattern already used
    in usage.py and admin.py -- avoids a SQLite-vs-Postgres dialect
    split for something this simple. Raw counts, not rates -- see
    MonthlyTrendPoint's own docstring for why."""
    _require_scope_admin(db, organization_id, user.id, None)
    months = max(1, min(months, 24))

    now = datetime.utcnow()
    month_keys = []
    cursor = now.replace(day=1)
    for _ in range(months):
        month_keys.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_keys.reverse()
    earliest = datetime.strptime(month_keys[0], "%Y-%m")

    def _bucket(timestamps: list[datetime]) -> dict[str, int]:
        counts = {m: 0 for m in month_keys}
        for ts in timestamps:
            key = ts.strftime("%Y-%m")
            if key in counts:
                counts[key] += 1
        return counts

    app_ids = [a.id for a in db.query(models.Application.id).filter_by(organization_id=organization_id).all()]

    joined_ts = [a.created_at for a in db.query(models.Application.created_at).filter(
        models.Application.organization_id == organization_id, models.Application.created_at >= earliest,
    ).all()]
    checklist_ts = [c.completed_at for c in db.query(models.ChecklistCompletion.completed_at).filter(
        models.ChecklistCompletion.application_id.in_(app_ids), models.ChecklistCompletion.completed_at >= earliest,
    ).all()] if app_ids else []
    assignment_ids = [a.id for a in db.query(models.MentorAssignment.id).filter(models.MentorAssignment.application_id.in_(app_ids)).all()] if app_ids else []
    meeting_ts = [m.created_at for m in db.query(models.MentorMeetingLog.created_at).filter(
        models.MentorMeetingLog.mentor_assignment_id.in_(assignment_ids), models.MentorMeetingLog.created_at >= earliest,
    ).all()] if assignment_ids else []
    cert_ts = [c.completed_at for c in db.query(models.EmployeeCertification.completed_at).filter(
        models.EmployeeCertification.application_id.in_(app_ids), models.EmployeeCertification.completed_at >= earliest,
    ).all()] if app_ids else []

    joined_by_month = _bucket(joined_ts)
    checklist_by_month = _bucket(checklist_ts)
    meetings_by_month = _bucket(meeting_ts)
    certs_by_month = _bucket(cert_ts)

    return schemas.OrgAnalyticsTrends(points=[
        schemas.MonthlyTrendPoint(
            month=m, employees_joined=joined_by_month[m], checklist_completions=checklist_by_month[m],
            mentor_meetings_logged=meetings_by_month[m], certification_completions=certs_by_month[m],
        )
        for m in month_keys
    ])


@router.get("/{organization_id}/analytics/benchmark", response_model=schemas.OrgBenchmark)
def get_org_benchmark(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Anonymized, cross-org comparison -- same MIN_SAMPLE_SIZE
    discipline as rise_index.py's company_stats(): the benchmark only
    computes once enough OTHER orgs (this one excluded) have real
    onboarding activity to average across safely. No org names, no
    per-org breakdown ever returned -- just one aggregate number this
    org's own figure gets compared against."""
    from app.services.rise_index import MIN_SAMPLE_SIZE

    _require_scope_admin(db, organization_id, user.id, None)

    this_org_apps = db.query(models.Application).filter_by(organization_id=organization_id).all()
    this_org_app_ids = [a.id for a in this_org_apps]
    this_org_items = db.query(models.OrgChecklistItem).filter_by(organization_id=organization_id).all()
    this_org_completions = db.query(models.ChecklistCompletion).filter(
        models.ChecklistCompletion.application_id.in_(this_org_app_ids)
    ).count() if this_org_app_ids else 0
    denom = len(this_org_apps) * len(this_org_items)
    your_checklist_pct = round(this_org_completions / denom * 100, 1) if denom else 0.0

    this_org_assignments = db.query(models.MentorAssignment).filter(
        models.MentorAssignment.application_id.in_(this_org_app_ids)
    ).all() if this_org_app_ids else []
    this_org_assignment_ids = [a.id for a in this_org_assignments]
    this_org_meetings = db.query(models.MentorMeetingLog).filter(
        models.MentorMeetingLog.mentor_assignment_id.in_(this_org_assignment_ids)
    ).count() if this_org_assignment_ids else 0
    your_avg_meetings = round(this_org_meetings / len(this_org_assignments), 1) if this_org_assignments else 0.0

    # Every OTHER org with at least one employee -- computed the same
    # way, one org at a time, so the average is an average of PER-ORG
    # rates (not one giant pooled calculation that a single very large
    # org could dominate).
    other_org_ids = [
        o.id for o in db.query(models.Organization.id).filter(models.Organization.id != organization_id).all()
    ]
    other_checklist_pcts = []
    other_meeting_avgs = []
    for other_id in other_org_ids:
        apps = db.query(models.Application).filter_by(organization_id=other_id).all()
        if not apps:
            continue
        app_ids = [a.id for a in apps]
        items = db.query(models.OrgChecklistItem).filter_by(organization_id=other_id).all()
        completions = db.query(models.ChecklistCompletion).filter(models.ChecklistCompletion.application_id.in_(app_ids)).count()
        d = len(apps) * len(items)
        if d:
            other_checklist_pcts.append(completions / d * 100)

        assignments = db.query(models.MentorAssignment).filter(models.MentorAssignment.application_id.in_(app_ids)).all()
        if assignments:
            assignment_ids = [a.id for a in assignments]
            meetings = db.query(models.MentorMeetingLog).filter(models.MentorMeetingLog.mentor_assignment_id.in_(assignment_ids)).count()
            other_meeting_avgs.append(meetings / len(assignments))

    sample_size = len(other_checklist_pcts)
    avg_checklist_pct = round(sum(other_checklist_pcts) / len(other_checklist_pcts), 1) if sample_size >= MIN_SAMPLE_SIZE else None
    avg_meetings = round(sum(other_meeting_avgs) / len(other_meeting_avgs), 1) if len(other_meeting_avgs) >= MIN_SAMPLE_SIZE else None

    return schemas.OrgBenchmark(
        sample_size=sample_size, your_checklist_completion_pct=your_checklist_pct,
        avg_checklist_completion_pct=avg_checklist_pct,
        your_avg_meetings_per_pairing=your_avg_meetings, avg_meetings_per_pairing=avg_meetings,
    )


@router.get("/{organization_id}/analytics/export.pdf")
def org_analytics_pdf(
    organization_id: int,
    sections: str = "checklist,lessons,qa_gaps,departments,mentorship",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """A customizable report, not just the always-everything CSV above:
    the admin picks which sections to include via the `sections` query
    param (comma-separated, e.g. 'mentorship,departments'), and gets a
    formatted PDF with just those. Same underlying analytics query as
    the JSON/CSV endpoints -- this only changes what's rendered and
    how, not what's computed.

    Unrecognized section names are silently dropped rather than
    erroring -- a stale bookmarked URL or a frontend/backend version
    mismatch on section names shouldn't break report generation,
    it should just mean that section doesn't appear."""
    _require_admin(db, organization_id, user.id)
    analytics = org_analytics(organization_id, db, user)

    requested = {s.strip() for s in sections.split(",") if s.strip()}
    from app.services.analytics_export import VALID_SECTIONS
    selected = requested & VALID_SECTIONS

    org_row = db.query(models.Organization).filter_by(id=organization_id).first()

    from app.services import analytics_export
    pdf_bytes = analytics_export.generate_analytics_pdf(
        org_name=org_row.name if org_row else "Organization", analytics=analytics, sections=selected,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="riseply_org_{organization_id}_report.pdf"'},
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
    writer.writerow(["Pairings ended", m.pairings_ended])
    writer.writerow(["Would recommend mentor (%)", m.would_recommend_mentor_pct if m.would_recommend_mentor_pct is not None else "N/A"])
    writer.writerow(["Group relationships", m.total_group_relationships])
    writer.writerow(["Reciprocal relationships", m.total_reciprocal_relationships])
    writer.writerow(["Group/reciprocal meetings logged", m.total_relationship_meetings_logged])

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
    mentor_ended_ats: dict[int, object] = {}
    if app_ids:
        assignments = db.query(models.MentorAssignment).filter(models.MentorAssignment.application_id.in_(app_ids)).all()
        contact_ids = [a.contact_id for a in assignments]
        contacts_by_id = {c.id: c.name for c in db.query(models.OrgHumanContact).filter(models.OrgHumanContact.id.in_(contact_ids)).all()} if contact_ids else {}
        for a in assignments:
            mentor_names[a.application_id] = contacts_by_id.get(a.contact_id)
            mentor_assignment_ids[a.application_id] = a.id
            mentor_ended_ats[a.application_id] = a.ended_at

    return [
        schemas.OrgEmployeeOut(
            application_id=app_row.id, user_email=user_row.email,
            user_full_name=user_row.full_name or user_row.email,
            department_id=app_row.department_id,
            department_name=dept_names.get(app_row.department_id) if app_row.department_id else None,
            joined_at=app_row.created_at,
            mentor_name=mentor_names.get(app_row.id),
            mentor_assignment_id=mentor_assignment_ids.get(app_row.id),
            mentor_ended_at=mentor_ended_ats.get(app_row.id),
        )
        for app_row, user_row in rows
    ]


@router.get("/{organization_id}/my-reports", response_model=list[schemas.DirectReportOut])
def list_my_direct_reports(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """A genuinely separate, narrower tier from admin access -- no
    _require_admin/_require_scope_admin call here at all. Any logged-in
    user can call this; the query itself is self-scoping (it can only
    ever return people whose Application.manager_email matches the
    caller's OWN email), so there's nothing to authorize beyond being
    logged in. Someone with zero direct reports just gets an empty
    list back, same as someone who's never been listed as a manager
    anywhere -- not a security boundary, since the response can never
    contain anyone else's data no matter what organization_id is
    passed.

    manager_email is populated on Application at join time from the
    roster upload's own manager_email column (see job_buddy.py's
    add_current_job) -- this reuses that existing field rather than
    introducing a new reporting-line concept; it was already being
    captured, just only ever used for a one-off checklist-completion
    notification until now."""
    reports = db.query(models.Application).filter_by(
        organization_id=organization_id, manager_email=user.email,
    ).all()
    if not reports:
        return []

    report_ids = [r.id for r in reports]
    users_by_id = {
        u.id: u for u in db.query(models.User).filter(
            models.User.id.in_([r.user_id for r in reports])
        ).all()
    }
    dept_names = {d.id: d.name for d in db.query(models.Department).filter_by(organization_id=organization_id).all()}

    # Checklist completion, per report -- same company-wide-plus-
    # department layering rule used everywhere else (content, lessons,
    # analytics), just computed for one specific application instead
    # of aggregated across the whole org.
    checklist_items = db.query(models.OrgChecklistItem).filter_by(organization_id=organization_id).all()
    completions = db.query(models.ChecklistCompletion).filter(
        models.ChecklistCompletion.application_id.in_(report_ids)
    ).all()
    completed_pairs = {(c.application_id, c.checklist_item_id) for c in completions}

    mentor_assignments = db.query(models.MentorAssignment).filter(
        models.MentorAssignment.application_id.in_(report_ids)
    ).all()
    mentor_contact_ids = [a.contact_id for a in mentor_assignments]
    contacts_by_id = {c.id: c.name for c in db.query(models.OrgHumanContact).filter(models.OrgHumanContact.id.in_(mentor_contact_ids)).all()} if mentor_contact_ids else {}
    mentor_by_app = {a.application_id: contacts_by_id.get(a.contact_id) for a in mentor_assignments}

    all_certs = db.query(models.EmployeeCertification).filter(
        models.EmployeeCertification.application_id.in_(report_ids)
    ).order_by(models.EmployeeCertification.completed_at.desc()).all()
    latest_cert_by_pair: dict[tuple[int, int], models.EmployeeCertification] = {}
    for cert in all_certs:
        key = (cert.application_id, cert.requirement_id)
        if key not in latest_cert_by_pair:
            latest_cert_by_pair[key] = cert

    cert_requirements = db.query(models.CertificationRequirement).filter_by(organization_id=organization_id).all()

    results = []
    for report in reports:
        user_row = users_by_id.get(report.user_id)
        if not user_row:
            continue

        applicable_items = [i for i in checklist_items if i.department_id is None or i.department_id == report.department_id]
        completed_items = [i for i in applicable_items if (report.id, i.id) in completed_pairs]
        checklist_pct = round(len(completed_items) / len(applicable_items) * 100, 1) if applicable_items else 0.0

        # Same company-wide-plus-department layering as everywhere
        # else -- which requirements actually apply to THIS report,
        # not just which ones they happen to have a completion record
        # for.
        applicable_certs = [r for r in cert_requirements if r.department_id is None or r.department_id == report.department_id]
        certs_total = len(applicable_certs)
        certs_completed = certs_expired = 0
        for req in applicable_certs:
            latest = latest_cert_by_pair.get((report.id, req.id))
            if latest is None:
                continue
            if latest.expires_at and latest.expires_at < datetime.utcnow():
                certs_expired += 1
            else:
                certs_completed += 1

        results.append(schemas.DirectReportOut(
            application_id=report.id, user_full_name=user_row.full_name or user_row.email,
            user_email=user_row.email,
            department_name=dept_names.get(report.department_id) if report.department_id else None,
            checklist_completion_pct=checklist_pct,
            mentor_name=mentor_by_app.get(report.id),
            certifications_completed=certs_completed, certifications_total=certs_total,
            certifications_expired=certs_expired,
        ))

    return results


@router.get("/{organization_id}/my-pending-approvals", response_model=list[schemas.InternalJobApplicationOut])
def list_my_pending_approvals(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Same self-scoping-by-manager_email access pattern as
    list_my_direct_reports and decide_internal_job_application below --
    no admin check, the query itself can only ever return applications
    routed to THIS caller. Lets a manager actually discover what's
    waiting on them, rather than needing to already know an
    application_id to call decide() with."""
    rows = (
        db.query(models.InternalJobApplication, models.InternalJobPosting, models.Application, models.User)
        .join(models.InternalJobPosting, models.InternalJobApplication.posting_id == models.InternalJobPosting.id)
        .join(models.User, models.InternalJobApplication.applicant_user_id == models.User.id)
        .join(models.Application, (models.Application.user_id == models.InternalJobApplication.applicant_user_id) & (models.Application.organization_id == organization_id))
        .filter(
            models.InternalJobPosting.organization_id == organization_id,
            models.InternalJobApplication.status == "pending_approval",
            models.Application.manager_email == user.email,
        )
        .order_by(models.InternalJobApplication.submitted_at.desc())
        .all()
    )
    return [
        schemas.InternalJobApplicationOut(
            id=job_app.id, posting_id=job_app.posting_id,
            applicant_name=user_row.full_name or user_row.email, applicant_email=user_row.email,
            note=job_app.note, submitted_at=job_app.submitted_at,
            status=job_app.status, decline_reason=job_app.decline_reason,
            posting_title=posting.title,
        )
        for job_app, posting, applicant_app, user_row in rows
    ]


@router.post("/{organization_id}/internal-job-applications/{application_id}/decide", response_model=schemas.InternalJobApplicationOut)
def decide_internal_job_application(
    organization_id: int,
    application_id: int,
    payload: schemas.InternalJobApplicationDecision,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Same self-scoping-by-manager_email access pattern as
    list_my_direct_reports above -- no _require_admin call. Only the
    specific manager this application was routed to can decide it: the
    check is that THIS caller's email matches the applicant's own
    Application.manager_email, not any kind of org-wide permission."""
    row = (
        db.query(models.InternalJobApplication, models.InternalJobPosting)
        .join(models.InternalJobPosting, models.InternalJobApplication.posting_id == models.InternalJobPosting.id)
        .filter(
            models.InternalJobApplication.id == application_id,
            models.InternalJobPosting.organization_id == organization_id,
        ).first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Internal job application not found.")
    application, posting = row

    applicant_app = db.query(models.Application).filter_by(
        user_id=application.applicant_user_id, organization_id=organization_id,
    ).first()
    if not applicant_app or applicant_app.manager_email != user.email:
        raise HTTPException(status_code=403, detail="You're not the manager this application was routed to.")

    if application.status != "pending_approval":
        raise HTTPException(status_code=400, detail="This application has already been decided.")

    application.status = "approved" if payload.approve else "declined"
    application.decided_by_user_id = user.id
    application.decided_at = datetime.utcnow()
    application.decline_reason = payload.reason if not payload.approve else ""
    db.commit()
    db.refresh(application)

    applicant = db.query(models.User).filter_by(id=application.applicant_user_id).first()
    return schemas.InternalJobApplicationOut(
        id=application.id, posting_id=application.posting_id,
        applicant_name=(applicant.full_name or applicant.email) if applicant else "Unknown",
        applicant_email=applicant.email if applicant else "",
        note=application.note, submitted_at=application.submitted_at,
        status=application.status, decline_reason=application.decline_reason,
    )


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
        # A reassignment starts a fresh, active pairing -- clear any
        # prior "ended" state from a previous mentor's tenure on this
        # same row rather than leaving a new pairing looking already
        # concluded (see MentorAssignment's docstring for why this row
        # gets reused rather than a new one being created).
        existing.ended_at = None
        existing.end_reason = ""
        assignment = existing
    else:
        assignment = models.MentorAssignment(application_id=application_id, contact_id=contact.id)
        db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return schemas.MentorAssignmentOut(
        id=assignment.id, contact_id=contact.id, name=contact.name, email=contact.email,
        description=contact.description, assigned_at=assignment.assigned_at,
        ended_at=assignment.ended_at, end_reason=assignment.end_reason,
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
    ranked = mentor_matcher.suggest_mentors(db, employee.resume_text or "", goal_text, mentors)
    return [schemas.SuggestedMentorOut(**r) for r in ranked]


@router.post("/{organization_id}/mentor-assignments/{assignment_id}/end", response_model=schemas.MentorAssignmentOut)
def end_mentor_assignment(
    organization_id: int,
    assignment_id: int,
    payload: schemas.MentorAssignmentEndRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin-only, deliberately -- ending a pairing is a program-
    management decision (the employee finished onboarding, is moving
    teams, etc.), not something either participant triggers
    unilaterally. This is what unlocks the employee's ability to
    submit a retrospective (see below) -- a retrospective is
    inherently about a CONCLUDED relationship."""
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    application = db.query(models.Application).filter_by(id=assignment.application_id).first()
    _require_scope_admin(db, organization_id, user.id, application.department_id if application else None)

    assignment.ended_at = datetime.utcnow()
    assignment.end_reason = payload.reason
    db.commit()
    db.refresh(assignment)

    contact = db.query(models.OrgHumanContact).filter_by(id=assignment.contact_id).first()
    return schemas.MentorAssignmentOut(
        id=assignment.id, contact_id=assignment.contact_id,
        name=contact.name if contact else "", email=contact.email if contact else "",
        description=contact.description if contact else "",
        assigned_at=assignment.assigned_at, ended_at=assignment.ended_at, end_reason=assignment.end_reason,
    )


@router.post("/{organization_id}/mentor-assignments/{assignment_id}/retrospective", response_model=schemas.MentorRetrospectiveOut)
def submit_mentor_retrospective(
    organization_id: int,
    assignment_id: int,
    payload: schemas.MentorRetrospectiveCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Employee-only (not the mentor, not an admin) -- same reasoning
    as meeting feedback: this is the employee's own honest reflection,
    and keeping it employee-owned is what makes candor possible. Only
    submittable once the pairing is marked ended -- see
    end_mentor_assignment above. One retrospective per assignment
    (enforced by the unique constraint on the model); resubmitting
    updates the existing one rather than erroring, since a person
    revising their own reflection after more thought is normal, not
    something to block."""
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    application = db.query(models.Application).filter_by(id=assignment.application_id).first()
    if not application or application.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the employee in this pairing can submit a retrospective.")

    if assignment.ended_at is None:
        raise HTTPException(status_code=400, detail="This pairing hasn't been marked ended yet -- ask your admin to close it out first.")

    retro = db.query(models.MentorRetrospective).filter_by(mentor_assignment_id=assignment_id).first()
    if retro is None:
        retro = models.MentorRetrospective(mentor_assignment_id=assignment_id)
        db.add(retro)

    retro.what_worked = payload.what_worked
    retro.what_didnt_work = payload.what_didnt_work
    retro.would_recommend_mentor = payload.would_recommend_mentor
    db.commit()
    db.refresh(retro)
    return retro


@router.get("/{organization_id}/mentor-assignments/{assignment_id}/retrospective", response_model=schemas.MentorRetrospectiveOut | None)
def get_mentor_retrospective(
    organization_id: int,
    assignment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Employee-only, same as submitting -- an admin or the mentor
    cannot read this even though they CAN see the meeting log's
    aggregate rating elsewhere; retrospective text is a step more
    candid than a 1-5 meeting rating and gets a correspondingly
    stricter privacy boundary."""
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    application = db.query(models.Application).filter_by(id=assignment.application_id).first()
    if not application or application.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the employee in this pairing can view their retrospective.")

    return db.query(models.MentorRetrospective).filter_by(mentor_assignment_id=assignment_id).first()


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


@router.get("/{organization_id}/mentor-assignments/{assignment_id}/meetings/export")
def export_mentor_meetings_pdf(
    organization_id: int,
    assignment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Downloadable/printable PDF of a pairing's meeting history --
    same access rule as list_mentor_meetings (employee, their assigned
    mentor, or an admin scoped to the employee's department), since
    this is just a different rendering of the same data, not a new
    disclosure boundary."""
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    _require_mentor_pairing_access(db, organization_id, user.id, assignment)

    application = db.query(models.Application).filter_by(id=assignment.application_id).first()
    employee = db.query(models.User).filter_by(id=application.user_id).first() if application else None
    contact = db.query(models.OrgHumanContact).filter_by(id=assignment.contact_id).first()

    meetings = (
        db.query(models.MentorMeetingLog)
        .filter_by(mentor_assignment_id=assignment_id)
        .order_by(models.MentorMeetingLog.meeting_date.desc())
        .all()
    )

    from app.services import mentor_export
    pdf_bytes = mentor_export.generate_meeting_history_pdf(
        employee_name=(employee.full_name or employee.email) if employee else "Employee",
        mentor_name=contact.name if contact else "Mentor",
        meetings=meetings,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="mentorship_meetings_{assignment_id}.pdf"'},
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


@router.post("/{organization_id}/mentor-assignments/{assignment_id}/schedule", response_model=schemas.MentorMeetingScheduleOut)
def schedule_mentor_meeting(
    organization_id: int,
    assignment_id: int,
    payload: schemas.MentorMeetingScheduleCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Creates an UPCOMING meeting (see MentorMeetingSchedule's
    docstring for how this differs from the retrospective
    MentorMeetingLog) and, if either person in the pairing has a
    calendar connected, a real calendar event inviting both of them.

    Tries the SCHEDULER'S own connection first (the natural case --
    "I'm putting this on my calendar and inviting you"), falling back
    to the other party's connection if the scheduler doesn't have one
    connected but the other person does. Either way, Graph's
    /me/events invites whoever ISN'T the token owner as an attendee,
    so only one side needs to be connected for both people to get a
    real invite.

    A calendar failure (expired-beyond-refresh token, Graph API
    hiccup, neither party connected) does NOT fail the whole request
    -- the meeting still gets scheduled and saved, just without an
    auto-sent invite. Scheduling shouldn't be held hostage to a
    calendar integration being flaky; the person can always add it to
    their own calendar manually."""
    assignment = db.query(models.MentorAssignment).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorAssignment.id == assignment_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Mentor pairing not found.")

    _require_mentor_pairing_access(db, organization_id, user.id, assignment)

    application = db.query(models.Application).filter_by(id=assignment.application_id).first()
    employee = db.query(models.User).filter_by(id=application.user_id).first() if application else None
    contact = db.query(models.OrgHumanContact).filter_by(id=assignment.contact_id).first()
    mentor_user = db.query(models.User).filter_by(email=contact.email).first() if contact else None

    schedule = models.MentorMeetingSchedule(
        mentor_assignment_id=assignment_id, scheduled_by_user_id=user.id,
        scheduled_at=payload.scheduled_at, duration_minutes=payload.duration_minutes,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    # Scheduler's own connection first, then the other party's.
    candidate_users = [u for u in [user, employee, mentor_user] if u is not None]
    # De-dupe while preserving order (the scheduler might BE the
    # employee or the mentor, which would otherwise check the same
    # user's connection twice).
    seen_ids = set()
    candidate_users = [u for u in candidate_users if not (u.id in seen_ids or seen_ids.add(u.id))]

    attendee_emails = list(filter(None, {
        (employee.notify_email or employee.email) if employee else None,
        contact.email if contact else None,
    }))

    for candidate in candidate_users:
        connection = db.query(models.CalendarConnection).filter_by(user_id=candidate.id, provider="microsoft").first()
        if connection is None:
            continue
        try:
            access_token = calendar_oauth.get_valid_access_token(db, connection)
            # Exclude the token owner's own identifying emails --
            # Graph API's /me/events already lists them as organizer,
            # no need to also list them as an attendee.
            candidate_emails = {candidate.email, candidate.notify_email or candidate.email}
            other_attendees = [e for e in attendee_emails if e not in candidate_emails]
            event_id = calendar_oauth.create_event(
                access_token,
                subject=f"Mentorship meeting — Riseply",
                start=payload.scheduled_at,
                duration_minutes=payload.duration_minutes,
                attendee_emails=other_attendees,
            )
            schedule.calendar_event_id = event_id
            schedule.calendar_provider = "microsoft"
            schedule.calendar_connection_user_id = candidate.id
            db.commit()
            break
        except HTTPException:
            # This candidate's connection didn't work (expired beyond
            # refresh, Graph API error) -- try the next one rather than
            # failing the whole schedule over one bad connection.
            continue

    return schemas.MentorMeetingScheduleOut(
        id=schedule.id, mentor_assignment_id=schedule.mentor_assignment_id,
        scheduled_at=schedule.scheduled_at, duration_minutes=schedule.duration_minutes,
        calendar_event_created=schedule.calendar_event_id is not None,
        cancelled_at=schedule.cancelled_at, created_at=schedule.created_at,
    )


@router.get("/{organization_id}/mentor-assignments/{assignment_id}/schedule", response_model=list[schemas.MentorMeetingScheduleOut])
def list_scheduled_meetings(
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

    rows = (
        db.query(models.MentorMeetingSchedule)
        .filter_by(mentor_assignment_id=assignment_id, cancelled_at=None)
        .order_by(models.MentorMeetingSchedule.scheduled_at.asc())
        .all()
    )
    return [
        schemas.MentorMeetingScheduleOut(
            id=s.id, mentor_assignment_id=s.mentor_assignment_id,
            scheduled_at=s.scheduled_at, duration_minutes=s.duration_minutes,
            calendar_event_created=s.calendar_event_id is not None,
            cancelled_at=s.cancelled_at, created_at=s.created_at,
        )
        for s in rows
    ]


@router.delete("/{organization_id}/mentor-meeting-schedules/{schedule_id}")
def cancel_scheduled_meeting(
    organization_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    schedule = db.query(models.MentorMeetingSchedule).join(
        models.MentorAssignment, models.MentorMeetingSchedule.mentor_assignment_id == models.MentorAssignment.id
    ).join(
        models.Application, models.MentorAssignment.application_id == models.Application.id
    ).filter(
        models.MentorMeetingSchedule.id == schedule_id,
        models.Application.organization_id == organization_id,
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Scheduled meeting not found.")

    assignment = db.query(models.MentorAssignment).filter_by(id=schedule.mentor_assignment_id).first()
    _require_mentor_pairing_access(db, organization_id, user.id, assignment)

    if schedule.calendar_event_id and schedule.calendar_connection_user_id:
        connection = db.query(models.CalendarConnection).filter_by(
            user_id=schedule.calendar_connection_user_id, provider=schedule.calendar_provider,
        ).first()
        if connection:
            try:
                access_token = calendar_oauth.get_valid_access_token(db, connection)
                calendar_oauth.cancel_event(access_token, schedule.calendar_event_id)
            except HTTPException:
                # Best-effort -- the schedule itself still gets
                # cancelled in our own records even if the calendar
                # side couldn't be reached; a stale calendar entry the
                # person deletes manually is a much smaller problem
                # than not being able to cancel at all.
                pass

    schedule.cancelled_at = datetime.utcnow()
    db.commit()
    return {"cancelled": True}


# --- Group / reciprocal mentoring relationships (additive to MentorAssignment's
# strict 1:1 shape -- see MentorshipRelationship's docstring for why this is a
# separate system rather than a migration of the existing one) ---

_relationship_out = mentorship_relationships.relationship_out
_require_relationship_access = mentorship_relationships.require_relationship_access


@router.post("/{organization_id}/mentorship-relationships", response_model=schemas.MentorshipRelationshipOut)
def create_mentorship_relationship(
    organization_id: int,
    payload: schemas.MentorshipRelationshipCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin-only, same as assign_mentor for 1:1 -- building a group or
    pairing is a program-management decision. No AI-assisted
    suggestion in this first pass (see MentorshipRelationship's
    docstring); the admin picks participants and roles directly."""
    _require_scope_admin(db, organization_id, user.id, None)

    if payload.relationship_type not in schemas.VALID_RELATIONSHIP_TYPES:
        raise HTTPException(status_code=400, detail=f"relationship_type must be one of: {', '.join(schemas.VALID_RELATIONSHIP_TYPES)}")

    for p in payload.participants:
        if p.role not in schemas.VALID_PARTICIPANT_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(schemas.VALID_PARTICIPANT_ROLES)}")
        application = db.query(models.Application).filter_by(id=p.application_id, organization_id=organization_id).first()
        if not application:
            raise HTTPException(status_code=404, detail=f"Employee (application {p.application_id}) not found in this organization.")

    if payload.relationship_type == "reciprocal" and any(p.role != "peer" for p in payload.participants):
        raise HTTPException(status_code=400, detail="Reciprocal relationships use role='peer' for every participant -- no mentor/mentee hierarchy.")

    relationship = models.MentorshipRelationship(
        organization_id=organization_id, relationship_type=payload.relationship_type, name=payload.name,
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)

    for p in payload.participants:
        db.add(models.MentorshipParticipant(relationship_id=relationship.id, application_id=p.application_id, role=p.role))
    db.commit()

    return _relationship_out(db, relationship)


@router.get("/{organization_id}/mentorship-relationships", response_model=list[schemas.MentorshipRelationshipOut])
def list_mentorship_relationships(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin-only listing (the org-wide view) -- an individual
    participant sees their own relationships through a different,
    narrower endpoint (see get_my_mentorship_relationships in
    job_buddy.py), not this one."""
    _require_scope_admin(db, organization_id, user.id, None)
    rows = db.query(models.MentorshipRelationship).filter_by(organization_id=organization_id).order_by(models.MentorshipRelationship.created_at.desc()).all()
    return [_relationship_out(db, r) for r in rows]


@router.post("/{organization_id}/mentorship-relationships/{relationship_id}/participants", response_model=schemas.MentorshipRelationshipOut)
def add_relationship_participant(
    organization_id: int,
    relationship_id: int,
    payload: schemas.MentorshipParticipantCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, None)
    relationship = db.query(models.MentorshipRelationship).filter_by(id=relationship_id, organization_id=organization_id).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Mentorship relationship not found.")
    if payload.role not in schemas.VALID_PARTICIPANT_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(schemas.VALID_PARTICIPANT_ROLES)}")
    application = db.query(models.Application).filter_by(id=payload.application_id, organization_id=organization_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Employee not found in this organization.")

    existing = db.query(models.MentorshipParticipant).filter_by(relationship_id=relationship_id, application_id=payload.application_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="This employee is already a participant in this relationship.")

    db.add(models.MentorshipParticipant(relationship_id=relationship_id, application_id=payload.application_id, role=payload.role))
    db.commit()
    return _relationship_out(db, relationship)


@router.delete("/{organization_id}/mentorship-relationships/{relationship_id}/participants/{participant_id}", response_model=schemas.MentorshipRelationshipOut)
def remove_relationship_participant(
    organization_id: int,
    relationship_id: int,
    participant_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, None)
    relationship = db.query(models.MentorshipRelationship).filter_by(id=relationship_id, organization_id=organization_id).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Mentorship relationship not found.")
    participant = db.query(models.MentorshipParticipant).filter_by(id=participant_id, relationship_id=relationship_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found in this relationship.")

    db.delete(participant)
    db.commit()
    return _relationship_out(db, relationship)


@router.post("/{organization_id}/mentorship-relationships/{relationship_id}/end", response_model=schemas.MentorshipRelationshipOut)
def end_mentorship_relationship(
    organization_id: int,
    relationship_id: int,
    payload: schemas.MentorshipRelationshipEndRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, None)
    relationship = db.query(models.MentorshipRelationship).filter_by(id=relationship_id, organization_id=organization_id).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Mentorship relationship not found.")

    relationship.ended_at = datetime.utcnow()
    relationship.end_reason = payload.reason
    db.commit()
    return _relationship_out(db, relationship)


@router.post("/{organization_id}/mentorship-relationships/{relationship_id}/meetings", response_model=schemas.MentorshipMeetingLogOut)
def log_mentorship_meeting(
    organization_id: int,
    relationship_id: int,
    payload: schemas.MentorshipMeetingLogCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    relationship = db.query(models.MentorshipRelationship).filter_by(id=relationship_id, organization_id=organization_id).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Mentorship relationship not found.")
    _require_relationship_access(db, organization_id, user.id, relationship)

    log = models.MentorshipMeetingLog(
        relationship_id=relationship_id, logged_by_user_id=user.id,
        meeting_date=payload.meeting_date, notes=payload.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/{organization_id}/mentorship-relationships/{relationship_id}/meetings", response_model=list[schemas.MentorshipMeetingLogOut])
def list_mentorship_meetings(
    organization_id: int,
    relationship_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    relationship = db.query(models.MentorshipRelationship).filter_by(id=relationship_id, organization_id=organization_id).first()
    if not relationship:
        raise HTTPException(status_code=404, detail="Mentorship relationship not found.")
    _require_relationship_access(db, organization_id, user.id, relationship)

    return (
        db.query(models.MentorshipMeetingLog)
        .filter_by(relationship_id=relationship_id)
        .order_by(models.MentorshipMeetingLog.meeting_date.desc())
        .all()
    )


# --- Internal job board (internal mobility -- distinct from the external,
# AI-matched job discovery pipeline; see InternalJobPosting's docstring) ---

_internal_posting_out = internal_jobs.posting_out


@router.post("/{organization_id}/internal-jobs", response_model=schemas.InternalJobPostingOut)
def create_internal_job_posting(
    organization_id: int,
    payload: schemas.InternalJobPostingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, payload.department_id)

    if payload.department_id is not None:
        dept = db.query(models.Department).filter_by(id=payload.department_id, organization_id=organization_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found in this organization.")

    posting = models.InternalJobPosting(
        organization_id=organization_id, title=payload.title, department_id=payload.department_id,
        description=payload.description, created_by_user_id=user.id,
    )
    db.add(posting)
    db.commit()
    db.refresh(posting)
    return _internal_posting_out(db, posting)


@router.get("/{organization_id}/internal-jobs", response_model=list[schemas.InternalJobPostingOut])
def list_internal_job_postings(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin view -- includes closed postings too (unlike the employee-
    facing browse endpoint in job_buddy.py, which only shows open
    ones)."""
    _require_scope_admin(db, organization_id, user.id, None)
    rows = db.query(models.InternalJobPosting).filter_by(organization_id=organization_id).order_by(models.InternalJobPosting.created_at.desc()).all()
    return [_internal_posting_out(db, p) for p in rows]


@router.post("/{organization_id}/internal-jobs/{posting_id}/close", response_model=schemas.InternalJobPostingOut)
def close_internal_job_posting(
    organization_id: int,
    posting_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    posting = db.query(models.InternalJobPosting).filter_by(id=posting_id, organization_id=organization_id).first()
    if not posting:
        raise HTTPException(status_code=404, detail="Internal job posting not found.")
    _require_scope_admin(db, organization_id, user.id, posting.department_id)

    posting.closed_at = datetime.utcnow()
    db.commit()
    return _internal_posting_out(db, posting)


@router.get("/{organization_id}/internal-jobs/{posting_id}/applicants", response_model=list[schemas.InternalJobApplicationOut])
def list_internal_job_applicants(
    organization_id: int,
    posting_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    posting = db.query(models.InternalJobPosting).filter_by(id=posting_id, organization_id=organization_id).first()
    if not posting:
        raise HTTPException(status_code=404, detail="Internal job posting not found.")
    _require_scope_admin(db, organization_id, user.id, posting.department_id)

    rows = (
        db.query(models.InternalJobApplication, models.User)
        .join(models.User, models.InternalJobApplication.applicant_user_id == models.User.id)
        .filter(models.InternalJobApplication.posting_id == posting_id)
        .order_by(models.InternalJobApplication.submitted_at.desc())
        .all()
    )
    return [
        schemas.InternalJobApplicationOut(
            id=app_row.id, posting_id=app_row.posting_id,
            applicant_name=user_row.full_name or user_row.email, applicant_email=user_row.email,
            note=app_row.note, submitted_at=app_row.submitted_at,
            status=app_row.status, decline_reason=app_row.decline_reason,
        )
        for app_row, user_row in rows
    ]


# --- Compliance certifications (recurring, expiring requirements --
# distinct from the one-time onboarding checklist below; see
# CertificationRequirement's own docstring for why) ---

_certification_out = certifications.requirement_out


@router.post("/{organization_id}/certification-requirements", response_model=schemas.CertificationRequirementOut)
def create_certification_requirement(
    organization_id: int,
    payload: schemas.CertificationRequirementCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_scope_admin(db, organization_id, user.id, payload.department_id)

    if payload.department_id is not None:
        dept = db.query(models.Department).filter_by(id=payload.department_id, organization_id=organization_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found in this organization.")

    requirement = models.CertificationRequirement(
        organization_id=organization_id, department_id=payload.department_id,
        name=payload.name, description=payload.description, content=payload.content,
        renewal_period_days=payload.renewal_period_days,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return _certification_out(db, requirement)


@router.get("/{organization_id}/certification-requirements", response_model=list[schemas.CertificationRequirementOut])
def list_certification_requirements(
    organization_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Admin view -- no single employee to check completion status
    against, so my_status/my_completed_at/etc. all stay None here. Use
    the {id}/completions endpoint below for who's actually completed
    each requirement."""
    _require_scope_admin(db, organization_id, user.id, None)
    rows = db.query(models.CertificationRequirement).filter_by(organization_id=organization_id).order_by(models.CertificationRequirement.created_at.desc()).all()
    return [_certification_out(db, r) for r in rows]


@router.delete("/{organization_id}/certification-requirements/{requirement_id}")
def delete_certification_requirement(
    organization_id: int,
    requirement_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    requirement = db.query(models.CertificationRequirement).filter_by(id=requirement_id, organization_id=organization_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Certification requirement not found.")
    _require_scope_admin(db, organization_id, user.id, requirement.department_id)

    db.delete(requirement)
    db.commit()
    return {"deleted": True}


@router.get("/{organization_id}/certification-requirements/{requirement_id}/completions", response_model=list[schemas.EmployeeCertificationOut])
def list_certification_completions(
    organization_id: int,
    requirement_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Every completion record for this requirement across the org --
    deliberately full history (every past completion, including
    lapsed/renewed ones), not just each employee's latest, since a
    real compliance record should show the whole trail, not just
    current status."""
    requirement = db.query(models.CertificationRequirement).filter_by(id=requirement_id, organization_id=organization_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Certification requirement not found.")
    _require_scope_admin(db, organization_id, user.id, requirement.department_id)

    rows = (
        db.query(models.EmployeeCertification, models.Application, models.User)
        .join(models.Application, models.EmployeeCertification.application_id == models.Application.id)
        .join(models.User, models.Application.user_id == models.User.id)
        .filter(models.EmployeeCertification.requirement_id == requirement_id)
        .order_by(models.EmployeeCertification.completed_at.desc())
        .all()
    )
    return [
        schemas.EmployeeCertificationOut(
            id=cert.id, application_id=cert.application_id, requirement_id=cert.requirement_id,
            applicant_name=user_row.full_name or user_row.email, applicant_email=user_row.email,
            completed_at=cert.completed_at, expires_at=cert.expires_at,
            verified_by_user_id=cert.verified_by_user_id, verified_at=cert.verified_at,
        )
        for cert, app_row, user_row in rows
    ]


@router.post("/{organization_id}/employee-certifications/{completion_id}/verify", response_model=schemas.EmployeeCertificationOut)
def verify_employee_certification(
    organization_id: int,
    completion_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Deliberately a separate action from completing -- "the employee
    says they did it" and "an admin confirmed it" are two different
    states for a real compliance record, not collapsed into one
    boolean. See EmployeeCertification's own docstring."""
    row = (
        db.query(models.EmployeeCertification, models.CertificationRequirement)
        .join(models.CertificationRequirement, models.EmployeeCertification.requirement_id == models.CertificationRequirement.id)
        .filter(
            models.EmployeeCertification.id == completion_id,
            models.CertificationRequirement.organization_id == organization_id,
        ).first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Certification completion not found.")
    cert, requirement = row
    _require_scope_admin(db, organization_id, user.id, requirement.department_id)

    cert.verified_by_user_id = user.id
    cert.verified_at = datetime.utcnow()
    db.commit()
    db.refresh(cert)

    application = db.query(models.Application).filter_by(id=cert.application_id).first()
    user_row = db.query(models.User).filter_by(id=application.user_id).first() if application else None
    return schemas.EmployeeCertificationOut(
        id=cert.id, application_id=cert.application_id, requirement_id=cert.requirement_id,
        applicant_name=(user_row.full_name or user_row.email) if user_row else "Unknown",
        applicant_email=user_row.email if user_row else "",
        completed_at=cert.completed_at, expires_at=cert.expires_at,
        verified_by_user_id=cert.verified_by_user_id, verified_at=cert.verified_at,
    )


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
