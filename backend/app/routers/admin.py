from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.security import (
    get_current_admin, get_current_super_admin,
    require_admin_view, require_admin_action,
)
from app.services import admin_stats, notifier, discovery_sources
from app import models, schemas

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ADMIN_ROLES = {"super", "support", "billing", "readonly"}


# --- One-time bootstrap: no admin exists yet, so this can't require admin auth ---

@router.post("/bootstrap")
def bootstrap_admin(payload: schemas.AdminBootstrapRequest, db: Session = Depends(get_db)):
    if not settings.admin_bootstrap_secret or payload.secret != settings.admin_bootstrap_secret:
        raise HTTPException(status_code=403, detail="Invalid bootstrap secret.")

    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account with that email.")

    user.is_admin = True
    user.admin_role = "super"
    db.commit()
    return {"promoted": user.email, "admin_role": "super"}


# --- Admin management (super admins only) ---

@router.get("/admins", response_model=list[schemas.AdminUserOut])
def list_admins(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    """Any admin can see who else has admin access -- transparency about
    who holds elevated access isn't itself a sensitive action, only
    granting/revoking it is (that's gated separately, below)."""
    return db.query(models.User).filter_by(is_admin=True).order_by(models.User.email).all()


@router.post("/users/{user_id}/set-admin-role", response_model=schemas.AdminUserOut)
def set_admin_role(
    user_id: int,
    payload: schemas.AdminSetRoleRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_super_admin),
):
    """Grants, changes, or revokes admin access. role="" revokes it
    entirely. Only super admins can call this -- letting any admin role
    grant roles (including its own) would make the whole scheme
    meaningless."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't change your own admin role here.")
    if payload.role and payload.role not in VALID_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(sorted(VALID_ADMIN_ROLES))}")

    user = _get_target_user(db, user_id)
    if payload.role:
        user.is_admin = True
        user.admin_role = payload.role
    else:
        user.is_admin = False
        user.admin_role = ""
    db.commit()
    db.refresh(user)
    return user


# --- Users ---

@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_users(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("users", "billing")),
):
    limit = min(limit, 200)
    return db.query(models.User).order_by(
        models.User.created_at.desc()
    ).offset(offset).limit(limit).all()


def _get_target_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user with that ID.")
    return user


@router.post("/users/{user_id}/suspend", response_model=schemas.AdminUserOut)
def suspend_user(
    user_id: int,
    payload: schemas.AdminSuspendRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin_action("users")),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't suspend your own account.")
    user = _get_target_user(db, user_id)
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Remove admin access first before suspending an admin account.")
    user.is_suspended = True
    user.suspended_at = datetime.utcnow()
    user.suspended_reason = payload.reason
    db.commit()
    db.refresh(user)
    # Best-effort notice -- suspension takes effect immediately regardless
    # of whether the email goes through.
    try:
        notifier.send_email(
            user.notify_email or user.email,
            "Your Riseply account has been suspended",
            payload.reason or "Your account has been suspended. Contact support if you believe this is a mistake.",
        )
    except Exception:
        pass
    return user


@router.post("/users/{user_id}/unsuspend", response_model=schemas.AdminUserOut)
def unsuspend_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("users")),
):
    user = _get_target_user(db, user_id)
    user.is_suspended = False
    user.suspended_at = None
    user.suspended_reason = ""
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/refund")
def refund_user(
    user_id: int,
    payload: schemas.AdminRefundRequest,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("billing")),
):
    """Refunds the user's most recent Stripe charge. This only reaches
    out to Stripe -- it deliberately does NOT change subscription_tier or
    cancel the subscription itself, since a refund and a cancellation are
    different admin decisions; use the Stripe dashboard for cancellation."""
    user = _get_target_user(db, user_id)
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="This user has no billing account to refund.")
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing isn't configured yet — set STRIPE_SECRET_KEY on the server.")

    import stripe
    stripe.api_key = settings.stripe_secret_key
    charges = stripe.Charge.list(customer=user.stripe_customer_id, limit=1)
    if not charges.data:
        raise HTTPException(status_code=400, detail="No charges found for this user.")
    charge = charges.data[0]
    if charge.refunded:
        raise HTTPException(status_code=400, detail="That charge has already been refunded.")

    stripe.Refund.create(charge=charge.id, reason="requested_by_customer")
    return {"refunded": True, "charge_id": charge.id, "amount_usd": round(charge.amount / 100, 2), "reason": payload.reason}


# --- Overview: revenue / usage / errors ---

@router.get("/revenue", response_model=schemas.AdminRevenueOut)
def revenue(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    total_users = db.query(models.User).count()
    active_pro_count = db.query(models.User).filter_by(
        subscription_tier="pro", subscription_status="active"
    ).count()

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    signups_this_week = db.query(models.User).filter(models.User.created_at >= week_ago).count()
    signups_this_month = db.query(models.User).filter(models.User.created_at >= month_start).count()

    return schemas.AdminRevenueOut(
        total_users=total_users,
        free_count=total_users - active_pro_count,
        active_pro_count=active_pro_count,
        mrr_estimate_usd=round(active_pro_count * settings.pro_price_usd_display, 2),
        signups_this_week=signups_this_week,
        signups_this_month=signups_this_month,
    )


@router.get("/usage", response_model=schemas.AdminUsageOut)
def usage_stats(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    period = datetime.utcnow().strftime("%Y-%m")
    rows = db.query(
        models.UsageLog.action, func.sum(models.UsageLog.count)
    ).filter_by(period=period).group_by(models.UsageLog.action).all()

    by_action = {}
    total_cost = 0.0
    for action, count in rows:
        count = int(count or 0)
        cost = admin_stats.estimate_cost(action, count)
        by_action[action] = schemas.AdminUsageActionStat(count=count, estimated_cost_usd=cost)
        total_cost += cost

    return schemas.AdminUsageOut(
        period=period, by_action=by_action, total_estimated_cost_usd=round(total_cost, 2),
    )


@router.get("/errors", response_model=schemas.AdminErrorsOut)
def error_stats(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = db.query(
        models.FailureLog.action, func.count(models.FailureLog.id)
    ).filter(models.FailureLog.created_at >= month_start).group_by(models.FailureLog.action).all()

    by_action = [schemas.AdminFailureActionStat(action=a, count=int(c)) for a, c in rows]
    total = sum(s.count for s in by_action)

    return schemas.AdminErrorsOut(
        period=month_start.strftime("%Y-%m"), by_action=by_action, total_failures=total,
    )


# --- Support inbox ---

@router.get("/support-messages", response_model=list[schemas.AdminSupportMessageOut])
def list_support_messages(
    status: str | None = None,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("support")),
):
    q = db.query(models.SupportMessage, models.User.email).join(
        models.User, models.SupportMessage.user_id == models.User.id
    )
    if status:
        q = q.filter(models.SupportMessage.status == status)
    q = q.order_by(models.SupportMessage.created_at.desc())

    return [
        schemas.AdminSupportMessageOut(
            id=msg.id, user_email=email, subject=msg.subject, message=msg.message,
            status=msg.status, admin_reply=msg.admin_reply, replied_at=msg.replied_at,
            created_at=msg.created_at,
        )
        for msg, email in q.all()
    ]


@router.post("/support-messages/{message_id}/reply")
def reply_to_support_message(
    message_id: int,
    payload: schemas.AdminSupportReplyRequest,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("support")),
):
    msg = db.query(models.SupportMessage).filter_by(id=message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    user = db.query(models.User).filter_by(id=msg.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="The user who sent this no longer has an account.")

    try:
        notifier.send_email(
            user.notify_email or user.email,
            f"Re: {msg.subject}",
            payload.reply,
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Couldn't send the reply email -- the message was NOT marked resolved, try again.",
        )

    msg.admin_reply = payload.reply
    msg.replied_at = datetime.utcnow()
    msg.status = "resolved"
    db.commit()
    return {"replied": True}


# --- Organizations (Org Buddy as a Service / "Enterprise") ---

@router.get("/organizations", response_model=list[schemas.AdminOrganizationOut])
def list_organizations(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    orgs = db.query(models.Organization).order_by(models.Organization.created_at.desc()).all()

    base_price_by_plan = {
        "starter": settings.org_plan_starter_price_usd,
        "growth": settings.org_plan_growth_price_usd,
        # Enterprise has no fixed self-serve price yet (contact-us only) --
        # 0 here just means "not counted in the estimate", not "free".
        "enterprise": 0.0,
    }

    out = []
    for org in orgs:
        member_count = db.query(models.OrganizationMember).filter_by(organization_id=org.id).count()
        overage_seats = max(0, member_count - (org.included_seats or 0))
        is_billing = org.subscription_status == "active" and not org.is_sandbox
        base_price = base_price_by_plan.get(org.plan, 0.0) if is_billing else 0.0
        overage_cost = overage_seats * settings.org_plan_overage_price_per_seat_usd if is_billing else 0.0
        out.append(schemas.AdminOrganizationOut(
            id=org.id, name=org.name, plan=org.plan or "(none)",
            subscription_status=org.subscription_status or "inactive",
            included_seats=org.included_seats or 0, member_count=member_count,
            overage_seats=overage_seats,
            estimated_mrr_usd=round(base_price + overage_cost, 2),
            created_at=org.created_at, is_sandbox=org.is_sandbox,
        ))
    return out


# --- System health ---

@router.get("/system-health", response_model=schemas.AdminSystemHealthOut)
def system_health(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("health")),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    known_sources = (
        ["greenhouse", "lever"]
        + [f"rss:{f}" for f in discovery_sources.RSS_JOB_FEEDS]
    )

    rows = db.query(
        models.Job.source,
        func.count(models.Job.id).filter(models.Job.discovered_at >= day_ago),
        func.count(models.Job.id).filter(models.Job.discovered_at >= week_ago),
        func.max(models.Job.discovered_at),
    ).group_by(models.Job.source).all()

    by_source = {r[0]: r for r in rows}
    # RSS sources are keyed by feed *title* once discovered (not the feed
    # URL) -- fall back to whatever's actually in the DB for those, since
    # we can't know the title in advance without fetching the feed.
    seen_sources = set(by_source.keys()) | {s for s in known_sources if not s.startswith("rss:")}

    health = []
    for source in sorted(seen_sources):
        row = by_source.get(source)
        last_24h = int(row[1]) if row else 0
        last_7d = int(row[2]) if row else 0
        last_seen = row[3] if row else None
        if last_seen is None:
            status_label = "silent"
        elif last_seen >= day_ago:
            status_label = "healthy"
        elif last_seen >= week_ago:
            status_label = "stale"
        else:
            status_label = "silent"
        health.append(schemas.AdminJobSourceHealthOut(
            source=source, jobs_last_24h=last_24h, jobs_last_7d=last_7d,
            last_discovered_at=last_seen, status=status_label,
        ))

    total_jobs = db.query(models.Job).count()
    return schemas.AdminSystemHealthOut(job_sources=health, total_jobs_in_pool=total_jobs)


# --- Content moderation (Job Buddy safety flags) ---

@router.get("/flagged-messages", response_model=list[schemas.AdminFlaggedMessageOut])
def list_flagged_messages(
    resolved: bool | None = None,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("moderation")),
):
    q = db.query(models.JobBuddyMessage, models.User.email).join(
        models.User, models.JobBuddyMessage.user_id == models.User.id
    ).filter(models.JobBuddyMessage.flagged.is_(True))

    if resolved is True:
        q = q.filter(models.JobBuddyMessage.flag_resolved_at.isnot(None))
    elif resolved is False:
        q = q.filter(models.JobBuddyMessage.flag_resolved_at.is_(None))

    q = q.order_by(models.JobBuddyMessage.created_at.desc()).limit(200)

    return [
        schemas.AdminFlaggedMessageOut(
            id=msg.id, application_id=msg.application_id, user_email=email,
            role=msg.role, content=msg.content, flag_reason=msg.flag_reason,
            flag_resolved_at=msg.flag_resolved_at, created_at=msg.created_at,
        )
        for msg, email in q.all()
    ]


@router.post("/flagged-messages/{message_id}/resolve")
def resolve_flagged_message(
    message_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("moderation")),
):
    msg = db.query(models.JobBuddyMessage).filter_by(id=message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    msg.flag_resolved_at = datetime.utcnow()
    db.commit()
    return {"resolved": True}
