"""Shared logic for compliance certifications, used by both
routers/org_buddy.py (admin requirement management) and
routers/job_buddy.py (an employee's own status/completion view).

Lives here rather than in one router with the other importing from it
-- same reasoning as mentorship_relationships.py and internal_jobs.py:
a service module is the right home for logic more than one router
genuinely needs.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models, schemas


def requirement_out(
    db: Session, requirement: models.CertificationRequirement,
    application_id: int | None = None,
) -> schemas.CertificationRequirementOut:
    department = db.query(models.Department).filter_by(id=requirement.department_id).first() if requirement.department_id else None

    my_status = my_completed_at = my_expires_at = my_verified = None
    if application_id is not None:
        latest = (
            db.query(models.EmployeeCertification)
            .filter_by(application_id=application_id, requirement_id=requirement.id)
            .order_by(models.EmployeeCertification.completed_at.desc())
            .first()
        )
        if latest is None:
            my_status = "not_started"
        else:
            my_completed_at = latest.completed_at
            my_expires_at = latest.expires_at
            my_verified = latest.verified_at is not None
            my_status = "expired" if (latest.expires_at and latest.expires_at < datetime.utcnow()) else "completed"

    return schemas.CertificationRequirementOut(
        id=requirement.id, name=requirement.name, description=requirement.description,
        content=requirement.content, department_id=requirement.department_id,
        department_name=department.name if department else None,
        renewal_period_days=requirement.renewal_period_days, created_at=requirement.created_at,
        my_status=my_status, my_completed_at=my_completed_at, my_expires_at=my_expires_at, my_verified=my_verified,
    )


def complete_requirement(db: Session, application_id: int, requirement: models.CertificationRequirement) -> models.EmployeeCertification:
    """Creates a new completion record -- a genuinely new row, not an
    update to a prior one, even for a renewal of something already
    completed once. Preserves full history: an org can see not just
    that someone is currently compliant, but the whole record of past
    completions and whether earlier ones lapsed before being renewed."""
    completed_at = datetime.utcnow()
    expires_at = (
        completed_at + timedelta(days=requirement.renewal_period_days)
        if requirement.renewal_period_days else None
    )
    record = models.EmployeeCertification(
        application_id=application_id, requirement_id=requirement.id,
        content_snapshot=requirement.content, completed_at=completed_at, expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
