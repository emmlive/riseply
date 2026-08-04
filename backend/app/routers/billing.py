from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.security import get_current_user
from app import models

router = APIRouter(prefix="/billing", tags=["billing"])


class TipRequest(BaseModel):
    amount_usd: float = 5.0  # e.g. 5.00 for a $5 tip


@router.post("/tip-checkout")
def create_tip_checkout(payload: TipRequest, user: models.User = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Tipping isn't configured yet — set STRIPE_SECRET_KEY on the server.",
        )
    if payload.amount_usd < 1:
        raise HTTPException(status_code=400, detail="Minimum tip is $1.")

    import stripe
    stripe.api_key = settings.stripe_secret_key

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Tip — Job Application Agent"},
                "unit_amount": int(payload.amount_usd * 100),
            },
            "quantity": 1,
        }],
        customer_email=user.email,
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
    )
    return {"checkout_url": session.url}
