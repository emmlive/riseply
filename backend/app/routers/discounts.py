from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.security import require_admin_view, require_admin_action
from app.services import discounts as discount_service
from app import models, schemas

# Admin management of discount codes. Billing-role and super admins can
# create/disable; billing, super and read-only admins can view. Codes are
# never deleted (only deactivated) so redemption history stays intact.
router = APIRouter(prefix="/admin/discount-codes", tags=["admin", "discounts"])


def _out(db: Session, row: models.DiscountCode) -> schemas.DiscountCodeOut:
    count = discount_service.redemption_count(db, row.id)
    return schemas.DiscountCodeOut(
        id=row.id, code=row.code, kind=row.kind, percent_off=row.percent_off,
        amount_off_cents=row.amount_off_cents, duration=row.duration or "once",
        duration_months=row.duration_months, free_days=row.free_days,
        max_redemptions=row.max_redemptions, expires_at=row.expires_at,
        active=bool(row.active), note=row.note or "", created_at=row.created_at,
        redemption_count=count, status=discount_service.status_of(row, count),
        description=discount_service.describe(row),
    )


def _stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Billing isn't configured yet — set STRIPE_SECRET_KEY on the server to create Stripe discount codes.",
        )
    import stripe
    stripe.api_key = settings.stripe_secret_key
    return stripe


@router.get("", response_model=list[schemas.DiscountCodeOut])
def list_codes(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    rows = db.query(models.DiscountCode).order_by(models.DiscountCode.created_at.desc(), models.DiscountCode.id.desc()).all()
    return [_out(db, r) for r in rows]


@router.post("", response_model=schemas.DiscountCodeOut)
def create_code(
    payload: schemas.DiscountCodeCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin_action("billing")),
):
    code = discount_service.normalize(payload.code)
    if db.query(models.DiscountCode).filter_by(code=code).first():
        raise HTTPException(status_code=409, detail="A code with that name already exists.")
    if payload.expires_at and payload.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="The expiry date must be in the future.")

    coupon_id = promo_id = None
    if payload.kind == "stripe":
        stripe = _stripe()
        try:
            coupon_id, promo_id = discount_service.create_stripe_objects(stripe, payload)
        except HTTPException:
            raise
        except Exception as e:
            print(f"[discounts] Stripe code creation failed for {code}: {e}")
            raise HTTPException(
                status_code=502,
                detail="Stripe couldn't create that code (it may already exist there). Nothing was saved.",
            )

    row = models.DiscountCode(
        code=code, kind=payload.kind, percent_off=payload.percent_off,
        amount_off_cents=payload.amount_off_cents, duration=payload.duration,
        duration_months=payload.duration_months, free_days=payload.free_days,
        max_redemptions=payload.max_redemptions, expires_at=payload.expires_at,
        note=payload.note.strip(), stripe_coupon_id=coupon_id,
        stripe_promotion_code_id=promo_id, created_by=admin.id, active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(db, row)


@router.post("/{code_id}/active", response_model=schemas.DiscountCodeOut)
def set_active(
    code_id: int,
    payload: schemas.DiscountCodeActive,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_action("billing")),
):
    row = db.query(models.DiscountCode).filter_by(id=code_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Discount code not found.")
    if row.kind == "stripe" and row.stripe_promotion_code_id:
        # Keep Stripe in step so a disabled code can't be used there either.
        try:
            _stripe().PromotionCode.modify(row.stripe_promotion_code_id, active=payload.active)
        except HTTPException:
            raise
        except Exception as e:
            print(f"[discounts] Stripe toggle failed for {row.code}: {e}")
            raise HTTPException(status_code=502, detail="Couldn't update that code in Stripe. Nothing was changed.")
    row.active = payload.active
    db.commit()
    db.refresh(row)
    return _out(db, row)


@router.get("/{code_id}/redemptions", response_model=list[schemas.DiscountRedemptionOut])
def list_redemptions(
    code_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin_view("billing")),
):
    if not db.query(models.DiscountCode).filter_by(id=code_id).first():
        raise HTTPException(status_code=404, detail="Discount code not found.")
    rows = (
        db.query(models.DiscountRedemption, models.User.email)
        .join(models.User, models.User.id == models.DiscountRedemption.user_id)
        .filter(models.DiscountRedemption.code_id == code_id)
        .order_by(models.DiscountRedemption.redeemed_at.desc())
        .all()
    )
    return [schemas.DiscountRedemptionOut(email=email, redeemed_at=r.redeemed_at, detail=r.detail or "") for r, email in rows]
