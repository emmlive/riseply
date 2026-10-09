import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.security import (
    get_current_admin, get_current_super_admin,
    require_admin_view, require_admin_action,
)
from app.services import admin_stats, notifier, discovery_sources, usage
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
    except Exception as e:
        print(f"[admin] Suspension email failed for user {user.id}: {e}")
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


@router.post("/users/{user_id}/reset-usage")
def reset_user_usage(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("users")),
):
    """Clears every current-period usage counter (matches, tailored
    resumes, interview preps, etc.) for one user -- for unblocking a
    testing/demo account without permanently exempting it via
    is_admin (which would also grant Admin panel visibility, not
    ideal for an account used in a live customer demo), or for a
    legitimate support case where a bug ate someone's real usage.
    Deliberately resets ALL actions at once rather than one at a time
    -- the practical need here is "let this account keep working," not
    surgical per-action control."""
    user = _get_target_user(db, user_id)
    period = usage._current_period()
    deleted = db.query(models.UsageLog).filter_by(user_id=user_id, period=period).delete()
    db.commit()
    return {"reset": True, "actions_cleared": deleted}


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
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("support")),
):
    q = db.query(models.SupportMessage, models.User.email).join(
        models.User, models.SupportMessage.user_id == models.User.id
    )
    if status:
        q = q.filter(models.SupportMessage.status == status)
    if search:
        # Matches subject, message body, or the sender's email -- covers
        # the realistic ways an admin would actually search ("find that
        # billing thing from Jane") without needing separate fields.
        like = f"%{search}%"
        q = q.filter(
            (models.SupportMessage.subject.ilike(like))
            | (models.SupportMessage.message.ilike(like))
            | (models.User.email.ilike(like))
        )
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
    except Exception as e:
        print(f"[admin] Support reply email failed for message {message_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Couldn't send the reply email -- the message was NOT marked resolved, try again.",
        )

    msg.admin_reply = payload.reply
    msg.replied_at = datetime.utcnow()
    msg.status = "resolved"
    db.commit()
    return {"replied": True}


@router.post("/support-messages/{message_id}/resolve")
def resolve_support_message(
    message_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("support")),
):
    """Marks resolved without sending a reply -- for messages that don't
    need or warrant one ('good life', accidental submissions, spam-ish
    test messages), so clearing clutter doesn't force writing something
    to send just to make the Open queue shorter."""
    msg = db.query(models.SupportMessage).filter_by(id=message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    msg.status = "resolved"
    db.commit()
    return {"resolved": True}


@router.delete("/support-messages/{message_id}")
def delete_support_message(
    message_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("support")),
):
    msg = db.query(models.SupportMessage).filter_by(id=message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    db.delete(msg)
    db.commit()
    return {"deleted": True}


@router.get("/canned-replies", response_model=list[schemas.CannedReplyOut])
def list_canned_replies(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("support")),
):
    return db.query(models.CannedReply).order_by(models.CannedReply.title).all()


@router.post("/canned-replies", response_model=schemas.CannedReplyOut)
def create_canned_reply(
    payload: schemas.CannedReplyCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("support")),
):
    reply = models.CannedReply(title=payload.title, body=payload.body)
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply


@router.delete("/canned-replies/{reply_id}")
def delete_canned_reply(
    reply_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("support")),
):
    reply = db.query(models.CannedReply).filter_by(id=reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Canned reply not found.")
    db.delete(reply)
    db.commit()
    return {"deleted": True}


# --- Organizations (Org Buddy as a Service / "Enterprise") ---

@router.get("/enterprise-billing-requests", response_model=list[schemas.EnterpriseBillingRequestOut])
def list_all_enterprise_billing_requests(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    """Platform-wide view across every org -- the notification email
    sent when a request comes in can get lost; this is the durable,
    always-checkable source of truth."""
    return db.query(models.EnterpriseBillingRequest).order_by(models.EnterpriseBillingRequest.created_at.desc()).all()


@router.post("/enterprise-billing-requests/{request_id}/status")
def update_enterprise_billing_request_status(
    request_id: int,
    payload: schemas.EnterpriseBillingRequestStatusUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("billing")),
):
    req = db.query(models.EnterpriseBillingRequest).filter_by(id=request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if payload.status not in ("pending", "contacted", "resolved"):
        raise HTTPException(status_code=400, detail="Status must be pending, contacted, or resolved.")
    req.status = payload.status
    db.commit()
    return {"updated": True}


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

    # Every source we can pull from, so one that has never produced a job
    # still shows up (as silent) instead of being invisible.
    known_sources = ["greenhouse", "lever", "remoteok", "arbeitnow", "adzuna", "usajobs"]

    last_seen = func.coalesce(models.Job.last_seen_at, models.Job.discovered_at)
    rows = db.query(
        models.Job.source,
        func.count(models.Job.id).filter(models.Job.discovered_at >= day_ago),
        func.count(models.Job.id).filter(models.Job.discovered_at >= week_ago),
        func.max(last_seen),
        func.count(models.Job.id).filter(or_(models.Job.is_active.is_(None), models.Job.is_active.is_(True))),
    ).group_by(models.Job.source).all()

    by_source = {r[0]: r for r in rows}
    seen_sources = set(by_source.keys()) | set(known_sources)

    health = []
    for source in sorted(seen_sources):
        row = by_source.get(source)
        last_24h = int(row[1]) if row else 0
        last_7d = int(row[2]) if row else 0
        last_seen_at = row[3] if row else None
        active = int(row[4]) if row else 0
        if last_seen_at is None:
            status_label = "silent"
        elif last_seen_at >= day_ago:
            status_label = "healthy"
        elif last_seen_at >= week_ago:
            status_label = "stale"
        else:
            status_label = "silent"
        health.append(schemas.AdminJobSourceHealthOut(
            source=source, jobs_last_24h=last_24h, jobs_last_7d=last_7d, active_jobs=active,
            last_discovered_at=last_seen_at, status=status_label,
        ))

    warnings = []
    if not (settings.adzuna_app_id and settings.adzuna_app_key):
        warnings.append(
            "Adzuna (the biggest source, covering all industries) is switched off. "
            "Set ADZUNA_APP_ID and ADZUNA_APP_KEY on Render (free keys at developer.adzuna.com)."
        )
    if not (settings.usajobs_api_key and settings.usajobs_email):
        warnings.append(
            "USAJobs (US federal jobs) is switched off. Set USAJOBS_API_KEY and USAJOBS_EMAIL on Render "
            "(free at developer.usajobs.gov)."
        )

    if not settings.resend_api_key:
        warnings.append(
            "Email is switched off: RESEND_API_KEY isn't set on Render, so match emails, password resets and "
            "welcome emails are skipped without any error. Add it from your Resend dashboard (the SMTP_* "
            "variables are no longer used)."
        )

    # The most recent finished discovery run that recorded per-source results.
    last_at, last_kind, last_sources = None, "", []
    recent = db.query(models.ScheduledRunLog).filter(
        models.ScheduledRunLog.status == "success",
        models.ScheduledRunLog.run_type.in_(("scheduled_run", "interactive_discover")),
        models.ScheduledRunLog.result_json.isnot(None),
    ).order_by(models.ScheduledRunLog.finished_at.desc()).limit(10).all()
    for log in recent:
        try:
            result = json.loads(log.result_json)
        except (TypeError, ValueError):
            continue
        sources = (result.get("discovery") or result).get("sources") if isinstance(result, dict) else None
        if sources:
            last_at, last_kind, last_sources = log.finished_at, log.run_type, sources
            break
    last_discovery = [schemas.AdminDiscoverySourceRun(**{k: v for k, v in s.items() if k in schemas.AdminDiscoverySourceRun.model_fields}) for s in last_sources]
    for s in last_discovery:
        if s.status == "failed":
            warnings.append(f"{s.name} returned nothing in the last run: {s.notes[0] if s.notes else 'it failed'}")

    total_jobs = db.query(models.Job).count()
    active_jobs = db.query(models.Job).filter(or_(models.Job.is_active.is_(None), models.Job.is_active.is_(True))).count()
    return schemas.AdminSystemHealthOut(
        job_sources=health, total_jobs_in_pool=total_jobs, active_jobs_in_pool=active_jobs,
        warnings=warnings, last_discovery_at=last_at, last_discovery_kind=last_kind,
        last_discovery=last_discovery,
    )


@router.get("/email-health", response_model=schemas.AdminEmailHealthOut)
def email_health(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("health")),
):
    """Is email going out? Counts for the last day and week, and the most
    recent messages that were refused or skipped, with the reason."""
    now = datetime.utcnow()
    day_ago, week_ago = now - timedelta(hours=24), now - timedelta(days=7)

    def count(status: str, since):
        return db.query(models.EmailLog).filter(
            models.EmailLog.status == status, models.EmailLog.created_at >= since).count()

    problems = db.query(models.EmailLog).filter(
        models.EmailLog.status.in_(("failed", "skipped"))
    ).order_by(models.EmailLog.created_at.desc()).limit(10).all()
    return schemas.AdminEmailHealthOut(
        configured=bool(settings.resend_api_key),
        from_address=f"{settings.resend_from_name} <{settings.resend_from_email}>",
        sent_24h=count("sent", day_ago), failed_24h=count("failed", day_ago), skipped_24h=count("skipped", day_ago),
        sent_7d=count("sent", week_ago), failed_7d=count("failed", week_ago), skipped_7d=count("skipped", week_ago),
        recent_problems=[schemas.AdminEmailFailure(
            kind=r.kind or "other", to_addr=r.to_addr or "", subject=r.subject or "", status=r.status,
            error=r.error or "", created_at=r.created_at) for r in problems],
    )


@router.post("/email-test", response_model=schemas.AdminEmailTestOut)
def email_test(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin_action("health")),
):
    """Sends one real email to the signed-in admin, right now, and reports what
    the email provider said. The fastest way to find out whether email works."""
    to = admin.notify_email or admin.email
    try:
        result = notifier.send_email(
            to, "Riseply test email",
            "If you can read this, Riseply can send email. You can delete it.", kind="test")
    except Exception as e:  # noqa: BLE001
        return schemas.AdminEmailTestOut(ok=False, to=to, detail=str(e)[:500])
    if result == "skipped":
        return schemas.AdminEmailTestOut(
            ok=False, to=to,
            detail="Email is switched off: RESEND_API_KEY isn't set on the server.")
    return schemas.AdminEmailTestOut(
        ok=True, to=to,
        detail=f"Sent from {settings.resend_from_email}. Check the inbox (and spam) for {to}.")


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
