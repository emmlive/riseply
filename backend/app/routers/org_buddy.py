import csv
import io
import secrets
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.config import settings
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


def _require_member(db: Session, organization_id: int, user_id: int) -> models.OrganizationMember:
    """Admin OR employee -- used for things any org member should be able
    to see, like the human contacts list (an employee needs to see who
    they can request a handoff from)."""
    member = db.query(models.OrganizationMember).filter_by(
        organization_id=organization_id, user_id=user_id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="You're not a member of this organization.")
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
    """Expects a CSV with headers: email, title, tenure (tenure optional,
    defaults to just_started if blank/missing). Upserts by email -- a
    re-upload with updated info replaces the existing entry rather than
    duplicating it."""
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
        raise HTTPException(status_code=400, detail="CSV must have an 'email' column (title and tenure optional).")

    valid_tenures = {"just_started", "a_few_months", "well_established"}
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

        existing = db.query(models.OrgRosterEntry).filter_by(
            organization_id=organization_id, email=email
        ).first()
        if existing:
            existing.title = row.get("title", existing.title)
            existing.tenure = tenure
            updated += 1
        else:
            db.add(models.OrgRosterEntry(
                organization_id=organization_id, email=email,
                title=row.get("title", ""), tenure=tenure,
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
    conversation content. Same distinction as the usage stats endpoint:
    this is onboarding-coordination visibility, not a way to read
    anyone's chat with their buddy."""
    _require_admin(db, organization_id, user.id)
    rows = db.query(models.OrgRosterEntry).filter_by(organization_id=organization_id).all()
    return [
        schemas.OrgRosterEntryOut(
            id=r.id, email=r.email, title=r.title, tenure=r.tenure,
            joined=r.matched_user_id is not None, created_at=r.created_at,
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
    _require_admin(db, organization_id, user.id)
    contact = models.OrgHumanContact(
        organization_id=organization_id, name=payload.name,
        email=payload.email, description=payload.description,
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
    available before they can request a handoff to them."""
    _require_member(db, organization_id, user.id)
    return db.query(models.OrgHumanContact).filter_by(organization_id=organization_id).all()


@router.delete("/{organization_id}/contacts/{contact_id}")
def delete_contact(
    organization_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _require_admin(db, organization_id, user.id)
    contact = db.query(models.OrgHumanContact).filter_by(id=contact_id, organization_id=organization_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")
    db.delete(contact)
    db.commit()
    return {"deleted": True}


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
