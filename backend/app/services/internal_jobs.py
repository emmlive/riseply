"""Shared logic for the internal job board, used by both
routers/org_buddy.py (admin posting management) and routers/job_buddy.py
(an employee's own browse/apply view).

Lives here rather than in one router with the other importing from it --
same reasoning as mentorship_relationships.py and
calendar_oauth.get_valid_access_token: a service module is the right
home for logic more than one router genuinely needs.
"""
import re

from sqlalchemy.orm import Session

from app import models, schemas


def goal_matches_posting(goal_text: str, posting: models.InternalJobPosting) -> bool:
    """Simple keyword-overlap check, same lightweight technique used
    for keyword-priority job-candidate ordering in pipeline_runner.py
    -- not AI scoring, just "does this employee's stated career goal
    share any meaningful word with this posting's title or
    description." Deliberately not an AI call: this runs on every
    posting in a browse list, and a plain word-overlap signal is
    enough to surface "this might interest you" without needing the
    cost/latency of a real scoring call for something that's just a
    highlight, not a hard filter -- nothing gets hidden either way."""
    if not goal_text:
        return False

    def _words(text: str) -> set[str]:
        return {w for w in re.split(r"[\s\-/]+", text.lower()) if len(w) >= 3}

    goal_words = _words(goal_text)
    posting_words = _words(f"{posting.title} {posting.description}")
    return not goal_words.isdisjoint(posting_words)


def posting_out(
    db: Session, posting: models.InternalJobPosting,
    has_applied: bool | None = None, matches_your_goal: bool | None = None,
    my_application_status: str | None = None,
) -> schemas.InternalJobPostingOut:
    department = db.query(models.Department).filter_by(id=posting.department_id).first() if posting.department_id else None
    applicant_count = db.query(models.InternalJobApplication).filter_by(posting_id=posting.id).count()
    return schemas.InternalJobPostingOut(
        id=posting.id, title=posting.title, department_id=posting.department_id,
        department_name=department.name if department else None,
        description=posting.description, created_at=posting.created_at, closed_at=posting.closed_at,
        applicant_count=applicant_count, has_applied=has_applied, matches_your_goal=matches_your_goal,
        my_application_status=my_application_status,
    )
