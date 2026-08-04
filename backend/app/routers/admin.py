from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.security import get_current_admin
from app.services import admin_stats, notifier
from app import models, schemas

router = APIRouter(prefix="/admin", tags=["admin"])


# --- One-time bootstrap: no admin exists yet, so this can't require admin auth ---

@router.post("/bootstrap")
def bootstrap_admin(payload: schemas.AdminBootstrapRequest, db: Session = Depends(get_db)):
    if not settings.admin_bootstrap_secret or payload.secret != settings.admin_bootstrap_secret:
        raise HTTPException(status_code=403, detail="Invalid bootstrap secret.")

    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account with that email.")

    user.is_admin = True
    db.commit()
    return {"promoted": user.email}


# --- Everything below requires an existing admin ---

@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_users(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    limit = min(limit, 200)
    return db.query(models.User).order_by(
        models.User.created_at.desc()
    ).offset(offset).limit(limit).all()


@router.get("/revenue", response_model=schemas.AdminRevenueOut)
def revenue(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
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
    _admin: models.User = Depends(get_current_admin),
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
    _admin: models.User = Depends(get_current_admin),
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


@router.get("/support-messages", response_model=list[schemas.AdminSupportMessageOut])
def list_support_messages(
    status: str | None = None,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
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
    _admin: models.User = Depends(get_current_admin),
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
