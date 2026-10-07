"""Discount codes: validation, redemption, and Stripe object creation.

Two kinds (see models.DiscountCode): `stripe` codes become a Stripe
Coupon + Promotion Code and are applied at Checkout; `free_days` codes
grant complimentary Pro by setting User.pro_until. Error messages for
unusable codes are deliberately uniform ("isn't valid or has expired") so
the endpoints can't be used to probe which codes exist.
"""
import calendar
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

INVALID = "That code isn't valid or has expired."


def normalize(code: str) -> str:
    return (code or "").strip().upper()


def redemption_count(db: Session, code_id: int) -> int:
    return db.query(models.DiscountRedemption).filter_by(code_id=code_id).count()


def status_of(row: models.DiscountCode, count: int, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    if not row.active:
        return "disabled"
    if row.expires_at and row.expires_at <= now:
        return "expired"
    if row.max_redemptions is not None and count >= row.max_redemptions:
        return "exhausted"
    return "active"


def describe(row: models.DiscountCode) -> str:
    if row.kind == "free_days":
        return f"{row.free_days} days of Riseply Pro, free"
    amount = f"{row.percent_off}% off" if row.percent_off else f"${row.amount_off_cents / 100:,.2f} off"
    if row.duration == "forever":
        return f"{amount} Riseply Pro, every month"
    if row.duration == "repeating":
        n = row.duration_months or 1
        return f"{amount} Riseply Pro for {n} month{'s' if n != 1 else ''}"
    return f"{amount} your first Riseply Pro payment"


def find_usable(db: Session, code: str, user: models.User, kind: str | None = None) -> models.DiscountCode:
    """The code row if this user can use it right now; HTTP 400 otherwise.
    `kind` restricts to one kind (each endpoint handles only its own)."""
    row = db.query(models.DiscountCode).filter_by(code=normalize(code)).first()
    if not row or (kind and row.kind != kind):
        raise HTTPException(status_code=400, detail=INVALID)
    if status_of(row, redemption_count(db, row.id)) != "active":
        raise HTTPException(status_code=400, detail=INVALID)
    if db.query(models.DiscountRedemption).filter_by(code_id=row.id, user_id=user.id).first():
        raise HTTPException(status_code=400, detail="You've already used that code.")
    return row


def record_redemption(db: Session, row: models.DiscountCode, user: models.User, detail: str = "") -> bool:
    """Inserts the redemption; False if this user already redeemed the
    code (idempotent, so webhook retries are harmless). If a capped code
    went over its cap in a race, the new redemption is rolled back and
    False is returned."""
    db.add(models.DiscountRedemption(code_id=row.id, user_id=user.id, detail=detail))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    if row.max_redemptions is not None and redemption_count(db, row.id) > row.max_redemptions:
        db.rollback()
        return False
    db.commit()
    return True


def grant_free_days(db: Session, user: models.User, days: int) -> datetime:
    """Extends complimentary Pro by `days`, stacking onto any grant still
    running rather than overlapping it."""
    now = datetime.utcnow()
    start = user.pro_until if user.pro_until and user.pro_until > now else now
    user.pro_until = start + timedelta(days=days)
    return user.pro_until


def create_stripe_objects(stripe, data) -> tuple[str, str]:
    """Creates the Coupon and Promotion Code in Stripe; returns their ids.
    If the promotion code step fails, the coupon is removed again so
    nothing is left dangling. Stripe renamed how a promotion code points at
    its coupon in newer API versions (`promotion={"type":"coupon",...}`
    instead of `coupon=`), so the newer form is tried first with a fallback."""
    coupon_args = {"duration": data.duration, "name": f"Riseply {data.code.upper()}"[:40]}
    if data.percent_off is not None:
        coupon_args["percent_off"] = data.percent_off
    else:
        coupon_args.update(amount_off=data.amount_off_cents, currency="usd")
    if data.duration == "repeating":
        coupon_args["duration_in_months"] = data.duration_months
    coupon = stripe.Coupon.create(**coupon_args)

    promo_args = {"code": data.code.upper()}
    if data.max_redemptions is not None:
        promo_args["max_redemptions"] = data.max_redemptions
    if data.expires_at is not None:
        # Stored/treated as naive UTC (the schema normalizes it).
        promo_args["expires_at"] = calendar.timegm(data.expires_at.utctimetuple())
    try:
        try:
            promo = stripe.PromotionCode.create(promotion={"type": "coupon", "coupon": coupon.id}, **promo_args)
        except Exception as first:
            if "promotion" not in str(first).lower() and "unknown" not in str(first).lower() and "unrecognized" not in str(first).lower():
                raise
            promo = stripe.PromotionCode.create(coupon=coupon.id, **promo_args)
    except Exception:
        try:
            stripe.Coupon.delete(coupon.id)
        except Exception:
            pass
        raise
    return coupon.id, promo.id
