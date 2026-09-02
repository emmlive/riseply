"""Shared logic for group/reciprocal mentorship relationships, used by
both routers/org_buddy.py (admin management) and routers/job_buddy.py
(an employee's own view of relationships they participate in).

Lives here rather than in one router with the other importing from it
-- same reasoning as calendar_oauth.get_valid_access_token: a service
module is the right home for logic more than one router genuinely
needs, rather than picking one router to own it and having the other
reach into it.
"""
from sqlalchemy.orm import Session

from app import models, schemas


def relationship_out(db: Session, relationship: models.MentorshipRelationship) -> schemas.MentorshipRelationshipOut:
    participants = db.query(models.MentorshipParticipant).filter_by(relationship_id=relationship.id).all()
    participant_outs = []
    for p in participants:
        application = db.query(models.Application).filter_by(id=p.application_id).first()
        user = db.query(models.User).filter_by(id=application.user_id).first() if application else None
        participant_outs.append(schemas.MentorshipParticipantOut(
            id=p.id, application_id=p.application_id,
            user_full_name=(user.full_name or user.email) if user else "Unknown",
            role=p.role, added_at=p.added_at,
        ))
    return schemas.MentorshipRelationshipOut(
        id=relationship.id, relationship_type=relationship.relationship_type, name=relationship.name,
        participants=participant_outs, created_at=relationship.created_at,
        ended_at=relationship.ended_at, end_reason=relationship.end_reason,
    )


def require_relationship_access(db: Session, organization_id: int, user_id: int, relationship: models.MentorshipRelationship):
    """Same reasoning as org_buddy.py's _require_mentor_pairing_access
    for 1:1 -- any participant (any role, not just "mentor") can
    view/log for their own relationship without needing admin rights;
    anyone else needs to be an org admin.

    Imports _require_scope_admin from org_buddy.py locally (not at
    module level) to avoid a circular import: org_buddy.py itself
    imports from this module for relationship_out above, so a
    module-level import back the other way would deadlock at import
    time. A local import inside the function avoids that without
    needing a third module just to hold one shared admin-check
    helper."""
    from app.routers.org_buddy import _require_scope_admin

    participant_app_ids = [
        p.application_id for p in
        db.query(models.MentorshipParticipant).filter_by(relationship_id=relationship.id).all()
    ]
    if participant_app_ids:
        user_owns_a_participant_app = db.query(models.Application).filter(
            models.Application.id.in_(participant_app_ids), models.Application.user_id == user_id,
        ).first()
        if user_owns_a_participant_app:
            return
    _require_scope_admin(db, organization_id, user_id, None)
