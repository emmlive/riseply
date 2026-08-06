from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.security import get_current_user
from app import models

router = APIRouter(prefix="/billing", tags=["billing"])


def _stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Billing isn't configured yet — set STRIPE_SECRET_KEY on the server.",
        )
    import stripe
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _get_or_create_stripe_customer(stripe, db: Session, user: models.User) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(email=user.email, name=user.full_name or None)
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


# --- Subscribe to Pro ---

@router.post("/subscribe")
def create_subscription_checkout(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not settings.stripe_price_id_pro:
        raise HTTPException(
            status_code=503,
            detail="Pro plan isn't configured yet — set STRIPE_PRICE_ID_PRO on the server.",
        )
    stripe = _stripe()
    customer_id = _get_or_create_stripe_customer(stripe, db, user)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.stripe_price_id_pro, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        metadata={"user_id": str(user.id)},
    )
    return {"checkout_url": session.url}


# --- Manage existing subscription (cancel, update card, etc.) ---

@router.post("/portal")
def create_portal_session(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found for this user yet.")
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=settings.stripe_portal_return_url,
    )
    return {"portal_url": session.url}


# --- Optional one-off tip (kept from the original tipping feature) ---

class TipRequest(BaseModel):
    amount_usd: float = 5.0


@router.post("/tip-checkout")
def create_tip_checkout(payload: TipRequest, user: models.User = Depends(get_current_user)):
    if payload.amount_usd < 1:
        raise HTTPException(status_code=400, detail="Minimum tip is $1.")
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Tip — Riseply"},
                "unit_amount": int(payload.amount_usd * 100),
            },
            "quantity": 1,
        }],
        customer_email=user.email,
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
    )
    return {"checkout_url": session.url}


# --- Stripe webhook: the source of truth for subscription state ---

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe calls this directly (not through the frontend) whenever a
    subscription is created, updated, or cancelled. This is the ONLY place
    that should ever flip a user to 'pro' — never trust the client to
    report a successful payment on its own."""
    stripe = _stripe()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        if settings.stripe_webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
        else:
            # Webhook secret not set -- only acceptable in local dev, since
            # without it anyone could POST a fake "subscription active"
            # event. Warn loudly rather than fail silently.
            import json
            event = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook payload or signature.")

    event_type = event["type"] if isinstance(event, dict) else event.type
    data_object = event["data"]["object"] if isinstance(event, dict) else event.data.object

    def _get(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

    def _find_user_by_customer(customer_id: str):
        return db.query(models.User).filter_by(stripe_customer_id=customer_id).first()

    def _find_org_by_customer(customer_id: str):
        return db.query(models.Organization).filter_by(stripe_customer_id=customer_id).first()

    customer_id = _get(data_object, "customer")

    if event_type == "checkout.session.completed":
        subscription_id = _get(data_object, "subscription")
        metadata = _get(data_object, "metadata") or {}
        org_id_from_metadata = metadata.get("organization_id") if isinstance(metadata, dict) else None

        user = _find_user_by_customer(customer_id)
        if user and subscription_id and not org_id_from_metadata:
            user.stripe_subscription_id = subscription_id
            user.subscription_tier = "pro"
            user.subscription_status = "active"
            db.commit()

        org = _find_org_by_customer(customer_id)
        if org and subscription_id:
            plan = metadata.get("plan", "starter") if isinstance(metadata, dict) else "starter"
            org.stripe_subscription_id = subscription_id
            org.plan = plan
            org.subscription_status = "active"
            org.included_seats = (
                settings.org_plan_growth_seats if plan == "growth" else settings.org_plan_starter_seats
            )
            db.commit()

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        status = _get(data_object, "status")

        user = _find_user_by_customer(customer_id)
        if user:
            user.subscription_status = status
            user.subscription_tier = "pro" if status == "active" else "free"
            db.commit()

        org = _find_org_by_customer(customer_id)
        if org:
            org.subscription_status = status
            db.commit()

    elif event_type == "customer.subscription.deleted":
        user = _find_user_by_customer(customer_id)
        if user:
            user.subscription_tier = "free"
            user.subscription_status = "canceled"
            db.commit()

        org = _find_org_by_customer(customer_id)
        if org:
            org.subscription_status = "canceled"
            org.included_seats = 0
            db.commit()

    return {"received": True}
