import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.security import get_current_user
from app import models, schemas

router = APIRouter(prefix="/orgs", tags=["org-buddy"])


def _generate_join_code() -> str:
    return secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8].upper()


def _require_admin(db: Session, organization_id: int, user_id: int) -> models.OrganizationMember:
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user_id, role="admin"
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Admin access to this organization required.")
    return member


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
    # Extremely unlikely to collide given the entropy, but check anyway
    # rather than trust it blindly.
    while db.query(models.Organization).filter_by(join_code=join_code).first():
        join_code = _generate_join_code()

    org = models.Organization(name=payload.name, join_code=join_code)
    db.add(org)
    db.commit()
    db.refresh(org)

    db.add(models.OrganizationMember(organization_id=org.id, user_id=user.id, role="admin"))
    db.commit()
    return org


@router.get("/mine", response_model=list[schemas.OrganizationOut])
def my_organizations(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Orgs this user administers."""
    rows = db.query(models.Organization).join(
        models.OrganizationMember, models.OrganizationMember.organization_id == models.Organization.id
    ).filter(models.OrganizationMember.user_id == user.id, models.OrganizationMember.role == "admin").all()
    return rows


@router.post("/{organization_id}/content", response_model=schemas.OrgContentOut)
def add_org_content(
    organization_id: int,
    payload: schemas.OrgContentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_admin(db, organization_id, user.id)
    content = models.OrganizationBuddyContent(
        organization_id=organization_id, title=payload.title, content=payload.content,
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
    _require_admin(db, organization_id, user.id)
    return db.query(models.OrganizationBuddyContent).filter_by(organization_id=organization_id).all()


@router.delete("/{organization_id}/content/{content_id}")
def delete_org_content(
    organization_id: int,
    content_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_admin(db, organization_id, user.id)
    content = db.query(models.OrganizationBuddyContent).filter_by(
        id=content_id, organization_id=organization_id
    ).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found.")
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
