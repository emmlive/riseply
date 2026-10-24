"""What to do next, worked out from what the person already has.

No AI call and not metered: it only reads existing rows and returns at most
four suggestions, most useful first. Applications that belong to an employer
(organization_id set) are never included.

Every suggestion belongs to a stage of the career loop the whole product is
organised around: get_ready, find, apply, win, grow. journey() shows where the
person is along it.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app import models

QUIET_AFTER_DAYS = 7
MAX_ACTIONS = 4

STAGES = [
    ("get_ready", "Get ready", "Your resume and the answers forms ask for"),
    ("find", "Find", "Jobs that fit, scored against your resume"),
    ("apply", "Apply", "Tailor, autofill and track"),
    ("win", "Win", "Interview prep and practice"),
    ("grow", "Grow", "Close gaps, earn certifications, plan the next role"),
]


def _mine(db: Session, user_id: int):
    return db.query(models.Application).filter(
        models.Application.user_id == user_id,
        models.Application.organization_id.is_(None),
        models.Application.is_archived.is_(False),
        models.Application.deleted_at.is_(None),
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def build(db: Session, user: models.User) -> list[dict]:
    actions: list[dict] = []
    if not (user.resume_text or "").strip():
        return [{"key": "add_resume", "stage": "get_ready", "title": "Add your resume", "href": "/dashboard/resume", "cta": "Add resume",
                 "detail": "Matching, tailoring and every coaching tool start from your resume."}]

    # 1. Interviews with no prep yet: the most time-sensitive thing there is.
    interviewing = (
        _mine(db, user.id).filter(models.Application.status == "interviewing")
        .join(models.Job, models.Job.id == models.Application.job_id).add_entity(models.Job).all()
    )
    prepped = {
        r[0] for r in db.query(models.InterviewPrep.application_id)
        .filter(models.InterviewPrep.application_id.in_([a.id for a, _ in interviewing] or [0])).all()
    }
    for a, job in interviewing:
        if a.id not in prepped:
            actions.append({"key": f"prep-{a.id}", "stage": "win", "title": f"Get ready for your interview at {job.company}",
                            "detail": f"You haven't made interview prep for {job.title} yet. A mock interview is the best use of the time.",
                            "href": "/dashboard/applications", "cta": "Prepare"})
    if interviewing:
        actions.append({"key": "mock", "stage": "win", "title": "Practise a mock interview",
                        "detail": "Run one out loud in voice mode, then read the delivery feedback.",
                        "href": "/dashboard/career-coach?" + urlencode({"type": "interview", "role": interviewing[0][1].title[:120]}),
                        "cta": "Start practice"})

    # 2. Applications that have gone quiet.
    cutoff = datetime.utcnow() - timedelta(days=QUIET_AFTER_DAYS)
    quiet = _mine(db, user.id).filter(
        models.Application.status == "submitted", models.Application.submitted_at.isnot(None),
        models.Application.submitted_at <= cutoff,
    ).count()
    if quiet:
        actions.append({"key": "quiet", "stage": "apply", "title": f"Follow up on {_plural(quiet, 'application')}",
                        "detail": "No reply for a week or more. A short follow-up often gets one, and we'll draft it.",
                        "href": "/dashboard/applications", "cta": "Open applications"})

    # 3. Never searched, or matches waiting on a decision.
    if not user.used_welcome_search and not _mine(db, user.id).count():
        actions.append({"key": "first_search", "stage": "find", "title": "Find your first matches",
                        "detail": "Your first search is on us. Riseply scores real listings against your resume.",
                        "href": "/dashboard", "cta": "Go to Overview"})
    waiting = _mine(db, user.id).filter(models.Application.status == "pending_approval").count()
    if waiting:
        actions.append({"key": "review", "stage": "find", "title": f"Review {_plural(waiting, 'match')}",
                        "detail": "Rejecting with a reason teaches the matcher what to skip.",
                        "href": "/dashboard/applications", "cta": "Review"})

    # 4. The answers every form asks for, saved once for the extension.
    if not db.query(models.AutofillProfile.id).filter_by(user_id=user.id).first():
        actions.append({"key": "autofill_profile", "stage": "get_ready", "title": "Save the answers forms ask for",
                        "detail": "Work history, address and common questions, entered once. The browser extension fills them on every application.",
                        "href": "/dashboard/autofill-profile", "cta": "Set up"})

    # 5. Never looked at the gap to the role they want.
    if not db.query(models.SkillGapReport.id).filter_by(user_id=user.id).first():
        actions.append({"key": "skill_gap", "stage": "grow", "title": "See what's missing for your target role",
                        "detail": "Compare your resume with real listings and get a first exercise for each gap.",
                        "href": "/dashboard/skill-gap", "cta": "Find my gaps"})
    elif not db.query(models.CareerPathPlan.id).filter_by(user_id=user.id).first():
        actions.append({"key": "career_path", "stage": "grow", "title": "Plan your path to the role you want",
                        "detail": "A staged plan with something to build at each step.",
                        "href": "/dashboard/career-path", "cta": "Build my plan"})
    elif not db.query(models.ExamPrep.id).filter_by(user_id=user.id).first():
        actions.append({"key": "exam_prep", "stage": "grow", "title": "Studying for a certification?",
                        "detail": "Get an outline weighted like the real exam, practice questions, and a weekly study plan.",
                        "href": "/dashboard/exam-prep", "cta": "Start exam prep"})
    return actions[:MAX_ACTIONS]


def journey(db: Session, user: models.User, actions: list[dict] | None = None) -> dict:
    """Where the person is along the loop, one entry per stage:
    {"current": key, "stages": [{key, label, blurb, state, stat, href}]}.
    state is "done", "current" or "todo". Read-only, no AI call."""
    actions = build(db, user) if actions is None else actions
    has_resume = bool((user.resume_text or "").strip())
    has_autofill = bool(db.query(models.AutofillProfile.id).filter_by(user_id=user.id).first())
    mine = _mine(db, user.id)
    total = mine.count()
    waiting = mine.filter(models.Application.status == "pending_approval").count()
    sent = mine.filter(models.Application.status.in_(("submitted", "interviewing", "accepted"))).count()
    interviewing = mine.filter(models.Application.status == "interviewing").count()
    prepped = db.query(models.InterviewPrep.id).join(
        models.Application, models.Application.id == models.InterviewPrep.application_id
    ).filter(models.Application.user_id == user.id).count()
    has_gap = bool(db.query(models.SkillGapReport.id).filter_by(user_id=user.id).first())
    has_plan = bool(db.query(models.CareerPathPlan.id).filter_by(user_id=user.id).first())
    has_exam = bool(db.query(models.ExamPrep.id).filter_by(user_id=user.id).first())
    has_course = bool(db.query(models.CoachCourse.id).filter_by(user_id=user.id).filter(models.CoachCourse.archived_at.is_(None)).first())

    info = {
        "get_ready": (has_resume and has_autofill,
                      "Resume added" if has_resume and has_autofill else ("Add your resume" if not has_resume else "Save your form answers"),
                      "/dashboard/resume" if not has_resume else "/dashboard/autofill-profile"),
        "find": (bool(user.used_welcome_search) or total > 0,
                 f"{waiting} waiting" if waiting else (f"{total} found" if total else "Run your first search"),
                 "/dashboard/applications" if total else "/dashboard"),
        "apply": (sent > 0, f"{sent} sent" if sent else "Tailor and apply", "/dashboard/applications"),
        "win": (interviewing > 0 or prepped > 0,
                f"{interviewing} interviewing" if interviewing else ("Prep ready" if prepped else "Prepare for interviews"),
                "/dashboard/career-coach"),
        "grow": (has_gap or has_plan or has_exam or has_course,
                 "Plan under way" if (has_gap or has_plan or has_exam or has_course) else "Close your skill gaps",
                 "/dashboard/career-path" if has_gap else "/dashboard/skill-gap"),
    }
    keys = [k for k, _, _ in STAGES]
    current = actions[0]["stage"] if actions and actions[0].get("stage") in keys else next(
        (k for k in keys if not info[k][0]), "grow")
    stages = []
    for key, label, blurb in STAGES:
        done, stat, href = info[key]
        stages.append({"key": key, "label": label, "blurb": blurb, "stat": stat, "href": href,
                       "state": "current" if key == current else ("done" if done else "todo")})
    return {"current": current, "stages": stages}
