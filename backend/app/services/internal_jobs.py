"""Shared logic for the internal job board, used by both
routers/org_buddy.py (admin posting management) and routers/job_buddy.py
(an employee's own browse/apply view).

Lives here rather than in one router with the other importing from it --
same reasoning as mentorship_relationships.py and
calendar_oauth.get_valid_access_token: a service module is the right
home for logic more than one router genuinely needs.
"""
from sqlalchemy.orm import Session

from app import models, schemas


def posting_out(db: Session, posting: models.InternalJobPosting, has_applied: bool | None = None) -> schemas.InternalJobPostingOut:
    department = db.query(models.Department).filter_by(id=posting.department_id).first() if posting.department_id else None
    applicant_count = db.query(models.InternalJobApplication).filter_by(posting_id=posting.id).count()
    return schemas.InternalJobPostingOut(
        id=posting.id, title=posting.title, department_id=posting.department_id,
        department_name=department.name if department else None,
        description=posting.description, created_at=posting.created_at, closed_at=posting.closed_at,
        applicant_count=applicant_count, has_applied=has_applied,
    )
