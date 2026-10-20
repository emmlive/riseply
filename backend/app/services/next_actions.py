"""What to do next, worked out from what the person already has.

No AI call and not metered: it only reads existing rows and returns at most
four suggestions, most useful first. Applications that belong to an employer
(organization_id set) are never included.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app import models

QUIET_AFTER_DAYS = 7
MAX_ACTIONS = 4


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
        return [{"key": "add_resume", "title": "Add your resume", "href": "/dashboard/resume", "cta": "Add resume",
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
            actions.append({"key": f"prep-{a.id}", "title": f"Get ready for your interview at {job.company}",
                            "detail": f"You haven't made interview prep for {job.title} yet. A mock interview is the best use of the time.",
                            "href": "/dashboard/applications", "cta": "Prepare"})
    if interviewing:
        actions.append({"key": "mock", "title": "Practise a mock interview",
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
        actions.append({"key": "quiet", "title": f"Follow up on {_plural(quiet, 'application')}",
                        "detail": "No reply for a week or more. A short follow-up often gets one, and we'll draft it.",
                        "href": "/dashboard/applications", "cta": "Open applications"})

    # 3. Matches waiting on a decision.
    waiting = _mine(db, user.id).filter(models.Application.status == "pending_approval").count()
    if waiting:
        actions.append({"key": "review", "title": f"Review {_plural(waiting, 'match')}",
                        "detail": "Rejecting with a reason teaches the matcher what to skip.",
                        "href": "/dashboard/applications", "cta": "Review"})

    # 4. Never looked at the gap to the role they want.
    if not db.query(models.SkillGapReport.id).filter_by(user_id=user.id).first():
        actions.append({"key": "skill_gap", "title": "See what's missing for your target role",
                        "detail": "Compare your resume with real listings and get a first exercise for each gap.",
                        "href": "/dashboard/skill-gap", "cta": "Find my gaps"})
    elif not db.query(models.CareerPathPlan.id).filter_by(user_id=user.id).first():
        actions.append({"key": "career_path", "title": "Plan your path to the role you want",
                        "detail": "A staged plan with something to build at each step.",
                        "href": "/dashboard/career-path", "cta": "Build my plan"})
    return actions[:MAX_ACTIONS]
