from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user, require_admin_action, require_admin_view

# Person-facing: the Give feedback button and thumbs on Career Coach replies.
router = APIRouter(prefix="/feedback", tags=["feedback"])
# Admin-facing: read and triage it.
admin_router = APIRouter(prefix="/admin/feedback", tags=["admin"])

MAX_PER_DAY = 20          # general feedback per person per 24 hours
EXCERPT_CHARS = 400


@router.post("", status_code=201)
def send_feedback(
    payload: schemas.FeedbackIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(hours=24)
    recent = db.query(func.count(models.Feedback.id)).filter(
        models.Feedback.user_id == user.id, models.Feedback.kind == "general",
        models.Feedback.created_at >= since,
    ).scalar() or 0
    if recent >= MAX_PER_DAY:
        raise HTTPException(status_code=429, detail="You've sent a lot of feedback today. Thank you! Please try again tomorrow.")
    row = models.Feedback(
        user_id=user.id, kind="general", rating=payload.rating, category=payload.category,
        message=payload.message, page=payload.page,
    )
    db.add(row)
    db.commit()
    return {"ok": True}


@router.put("/coach-reply", response_model=schemas.CoachReplyFeedbackOut)
def rate_coach_reply(
    payload: schemas.CoachReplyFeedbackIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    msg = db.query(models.CareerCoachMessage).filter_by(id=payload.message_id, user_id=user.id, role="assistant").first()
    if not msg:
        raise HTTPException(status_code=404, detail="Reply not found.")
    row = db.query(models.Feedback).filter_by(user_id=user.id, message_id=msg.id).first()
    if row is None:
        row = models.Feedback(user_id=user.id, kind="coach_reply", message_id=msg.id, session_id=msg.session_id)
        db.add(row)
    row.helpful = payload.helpful
    # A thumbs-up carries no note; changing back to up clears an earlier one.
    row.message = "" if payload.helpful else payload.note
    row.status = "new"
    db.commit()
    return schemas.CoachReplyFeedbackOut(message_id=msg.id, helpful=payload.helpful)


@router.get("/coach-replies", response_model=list[schemas.CoachReplyFeedbackOut])
def my_coach_reply_ratings(
    session_id: int = Query(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows = db.query(models.Feedback).filter_by(user_id=user.id, kind="coach_reply", session_id=session_id).all()
    return [schemas.CoachReplyFeedbackOut(message_id=r.message_id, helpful=bool(r.helpful)) for r in rows]


# ---- Admin ------------------------------------------------------------------

@admin_router.get("", response_model=list[schemas.AdminFeedbackOut])
def list_feedback(
    kind: str | None = None,
    status: str | None = None,
    low: bool = False,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("support")),
):
    q = db.query(models.Feedback, models.User.email).join(models.User, models.Feedback.user_id == models.User.id)
    if kind in ("general", "coach_reply"):
        q = q.filter(models.Feedback.kind == kind)
    if status in ("new", "reviewed"):
        q = q.filter(models.Feedback.status == status)
    if low:   # 1-2 stars or a thumbs-down: where the problems are
        q = q.filter(((models.Feedback.rating <= 2) & (models.Feedback.rating.isnot(None))) | (models.Feedback.helpful.is_(False)))
    rows = q.order_by(models.Feedback.created_at.desc()).limit(limit).all()

    ids = [r.message_id for r, _ in rows if r.message_id]
    replies = {}
    if ids:
        replies = {m.id: m.content for m in db.query(models.CareerCoachMessage).filter(models.CareerCoachMessage.id.in_(ids)).all()}
    return [
        schemas.AdminFeedbackOut(
            id=r.id, user_email=email, kind=r.kind, rating=r.rating, helpful=r.helpful,
            category=r.category or "", message=r.message or "", page=r.page or "",
            reply_excerpt=(replies.get(r.message_id, "") or "")[:EXCERPT_CHARS],
            status=r.status or "new", created_at=r.created_at,
        )
        for r, email in rows
    ]


@admin_router.get("/summary", response_model=schemas.AdminFeedbackSummary)
def feedback_summary(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("support")),
):
    F = models.Feedback
    return schemas.AdminFeedbackSummary(
        total=db.query(func.count(F.id)).scalar() or 0,
        new=db.query(func.count(F.id)).filter(F.status == "new").scalar() or 0,
        avg_rating=(lambda v: round(float(v), 2) if v is not None else None)(
            db.query(func.avg(F.rating)).filter(F.rating.isnot(None)).scalar()),
        rated=db.query(func.count(F.id)).filter(F.rating.isnot(None)).scalar() or 0,
        thumbs_up=db.query(func.count(F.id)).filter(F.helpful.is_(True)).scalar() or 0,
        thumbs_down=db.query(func.count(F.id)).filter(F.helpful.is_(False)).scalar() or 0,
    )


@admin_router.post("/{feedback_id}/status")
def set_feedback_status(
    feedback_id: int,
    status: str = Query(..., pattern="^(new|reviewed)$"),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("support")),
):
    row = db.get(models.Feedback, feedback_id)
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    row.status = status
    db.commit()
    return {"ok": True}
