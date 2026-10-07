"""Tests for admin-managed discount codes (/admin/discount-codes) and
their redemption (/billing/check-code, /billing/redeem-code, and the
checkout + webhook path for Stripe-discount codes). Stripe is mocked.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.rate_limit import limiter
from app.security import get_current_user
from app import models
from app.services import usage, discounts

client = TestClient(app)
_n = [0]


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset():
    limiter.reset()
    yield
    app.dependency_overrides.clear()


def _user(db, admin=False, role=""):
    _n[0] += 1
    u = models.User(email=f"disc{_n[0]}@x.com", hashed_password="x", full_name="T",
                    is_admin=admin, admin_role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(u):
    # Load the user inside the request's own DB session, like the real
    # get_current_user does, so the router's changes persist and are visible.
    uid = u.id
    from fastapi import Depends
    from app.database import get_db

    def override(db=Depends(get_db)):
        return db.query(models.User).filter_by(id=uid).first()

    app.dependency_overrides[get_current_user] = override


def _admin_create(admin, **over):
    _login(admin)
    _n[0] += 1
    body = {"code": f"CODE{_n[0]}", "kind": "free_days", "free_days": 30, **over}
    return client.post("/admin/discount-codes", json=body)


# ---- validation -------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"code": "AB", "kind": "free_days", "free_days": 5},                              # too short
    {"code": "has space", "kind": "free_days", "free_days": 5},
    {"code": "OKAY1", "kind": "free_days"},                                           # no days
    {"code": "OKAY2", "kind": "free_days", "free_days": 5, "percent_off": 10},
    {"code": "OKAY3", "kind": "stripe"},                                              # no amount
    {"code": "OKAY4", "kind": "stripe", "percent_off": 10, "amount_off_cents": 500},  # both
    {"code": "OKAY5", "kind": "stripe", "percent_off": 101},
    {"code": "OKAY6", "kind": "stripe", "percent_off": 10, "duration": "repeating"},  # no months
    {"code": "OKAY7", "kind": "stripe", "percent_off": 10, "free_days": 3},
])
def test_create_validation(db, body):
    _login(_user(db, admin=True))
    assert client.post("/admin/discount-codes", json=body).status_code == 422


# ---- permissions ------------------------------------------------------------

def test_only_billing_and_super_admins_can_create(db):
    member = _user(db)
    _login(member)
    assert client.get("/admin/discount-codes").status_code == 403
    for role, expected in [("support", 403), ("readonly", 403), ("billing", 200), ("", 200)]:
        assert _admin_create(_user(db, admin=True, role=role)).status_code == expected, role


def test_readonly_and_billing_can_view_but_support_cannot(db):
    code_id = _admin_create(_user(db, admin=True)).json()["id"]
    for role, expected in [("readonly", 200), ("billing", 200), ("support", 403)]:
        _login(_user(db, admin=True, role=role))
        assert client.get("/admin/discount-codes").status_code == expected, role
        assert client.get(f"/admin/discount-codes/{code_id}/redemptions").status_code == expected, role


# ---- free-days codes --------------------------------------------------------

def test_create_normalizes_and_rejects_duplicates_and_past_expiry(db):
    admin = _user(db, admin=True)
    r = _admin_create(admin, code="Launch_30")
    assert r.status_code == 200 and r.json()["code"] == "LAUNCH_30"
    assert r.json()["description"] == "30 days of Riseply Pro, free"
    assert _admin_create(admin, code="launch_30").status_code == 409
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    assert _admin_create(admin, expires_at=past).status_code == 400


def test_redeem_free_days_grants_pro_and_stacks(db):
    admin = _user(db, admin=True)
    a = _admin_create(admin, free_days=30).json()["code"]
    b = _admin_create(admin, free_days=10).json()["code"]
    user = _user(db)
    assert not usage.is_pro(user)
    _login(user)
    r = client.post("/billing/redeem-code", json={"code": a.lower()})
    assert r.status_code == 200
    db.refresh(user)
    assert usage.is_pro(user)
    first_until = user.pro_until
    assert timedelta(days=29) < first_until - datetime.utcnow() <= timedelta(days=30)
    # a second, different code adds on top of the running grant
    assert client.post("/billing/redeem-code", json={"code": b}).status_code == 200
    db.refresh(user)
    assert user.pro_until - first_until == timedelta(days=10)
    # same code twice is refused
    assert client.post("/billing/redeem-code", json={"code": a}).status_code == 400
    # /me exposes the date
    assert client.get("/me").json()["pro_until"] is not None


def test_grant_lapses_by_date(db):
    user = _user(db)
    user.pro_until = datetime.utcnow() + timedelta(hours=1)
    db.commit()
    assert usage.is_pro(user)
    user.pro_until = datetime.utcnow() - timedelta(seconds=1)
    assert not usage.is_pro(user)


def test_paying_subscriber_cannot_redeem_free_days(db):
    code = _admin_create(_user(db, admin=True)).json()["code"]
    payer = _user(db)
    payer.subscription_tier, payer.subscription_status = "pro", "active"
    db.commit()
    _login(payer)
    assert client.post("/billing/redeem-code", json={"code": code}).status_code == 400
    assert db.query(models.DiscountRedemption).filter_by(user_id=payer.id).count() == 0


def test_unusable_codes_all_give_the_same_error(db):
    admin = _user(db, admin=True)
    capped = _admin_create(admin, max_redemptions=1).json()
    disabled = _admin_create(admin).json()
    _login(admin)
    client.post(f"/admin/discount-codes/{disabled['id']}/active", json={"active": False})
    expired = _admin_create(admin, expires_at=(datetime.utcnow() + timedelta(seconds=30)).isoformat()).json()
    row = db.query(models.DiscountCode).filter_by(id=expired["id"]).first()
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    first = _user(db)
    _login(first)
    assert client.post("/billing/redeem-code", json={"code": capped["code"]}).status_code == 200
    second = _user(db)
    _login(second)
    messages = set()
    for code in [capped["code"], disabled["code"], expired["code"], "NOSUCHCODE"]:
        r = client.post("/billing/redeem-code", json={"code": code})
        assert r.status_code == 400
        messages.add(r.json()["detail"])
    assert messages == {discounts.INVALID}  # can't tell "exists" from "doesn't"
    assert client.get(f"/admin/discount-codes").status_code == 403  # sanity: non-admin


def test_status_and_redemption_list(db):
    admin = _user(db, admin=True)
    created = _admin_create(admin, max_redemptions=1).json()
    assert created["status"] == "active" and created["redemption_count"] == 0
    user = _user(db)
    _login(user)
    client.post("/billing/redeem-code", json={"code": created["code"]})
    _login(admin)
    listed = {c["id"]: c for c in client.get("/admin/discount-codes").json()}[created["id"]]
    assert listed["redemption_count"] == 1 and listed["status"] == "exhausted"
    red = client.get(f"/admin/discount-codes/{created['id']}/redemptions").json()
    assert [r["email"] for r in red] == [user.email]
    assert client.get("/admin/discount-codes/99999999/redemptions").status_code == 404
    # re-enabling toggles state back; an exhausted code stays exhausted
    off = client.post(f"/admin/discount-codes/{created['id']}/active", json={"active": False}).json()
    assert off["status"] == "disabled"


def test_check_code_previews_without_redeeming(db):
    code = _admin_create(_user(db, admin=True), free_days=14).json()["code"]
    user = _user(db)
    _login(user)
    r = client.post("/billing/check-code", json={"code": code})
    assert r.status_code == 200 and r.json()["kind"] == "free_days"
    assert "14 days" in r.json()["description"]
    assert db.query(models.DiscountRedemption).filter_by(user_id=user.id).count() == 0
    assert client.post("/billing/check-code", json={"code": "nope"}).status_code == 400


# ---- Stripe-discount codes --------------------------------------------------

def _fake_stripe():
    st = MagicMock()
    st.Coupon.create.return_value = MagicMock(id="coup_1")
    st.PromotionCode.create.return_value = MagicMock(id="promo_1")
    st.Customer.create.return_value = MagicMock(id="cus_1")
    st.checkout.Session.create.return_value = MagicMock(url="https://checkout.example/s")
    return st


def test_create_stripe_code_creates_coupon_and_promo(db):
    st = _fake_stripe()
    admin = _user(db, admin=True)
    _login(admin)
    with patch("app.routers.discounts._stripe", return_value=st):
        r = client.post("/admin/discount-codes", json={
            "code": "save20", "kind": "stripe", "percent_off": 20, "duration": "repeating",
            "duration_months": 3, "max_redemptions": 50,
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        })
    assert r.status_code == 200
    assert r.json()["description"] == "20% off Riseply Pro for 3 months"
    coupon_kwargs = st.Coupon.create.call_args.kwargs
    assert coupon_kwargs["percent_off"] == 20 and coupon_kwargs["duration_in_months"] == 3
    promo_kwargs = st.PromotionCode.create.call_args.kwargs
    assert promo_kwargs["code"] == "SAVE20" and promo_kwargs["max_redemptions"] == 50
    assert isinstance(promo_kwargs["expires_at"], int)
    row = db.query(models.DiscountCode).filter_by(code="SAVE20").first()
    assert (row.stripe_coupon_id, row.stripe_promotion_code_id) == ("coup_1", "promo_1")


def test_amount_off_uses_usd_cents_and_describes_dollars(db):
    st = _fake_stripe()
    _login(_user(db, admin=True))
    with patch("app.routers.discounts._stripe", return_value=st):
        r = client.post("/admin/discount-codes", json={"code": "FIVEOFF", "kind": "stripe", "amount_off_cents": 500})
    assert r.json()["description"] == "$5.00 off your first Riseply Pro payment"
    assert st.Coupon.create.call_args.kwargs["amount_off"] == 500
    assert st.Coupon.create.call_args.kwargs["currency"] == "usd"


def test_stripe_failure_saves_nothing_and_cleans_up_coupon(db):
    st = _fake_stripe()
    st.PromotionCode.create.side_effect = RuntimeError("boom")
    _login(_user(db, admin=True))
    with patch("app.routers.discounts._stripe", return_value=st):
        r = client.post("/admin/discount-codes", json={"code": "WILLFAIL", "kind": "stripe", "percent_off": 10})
    assert r.status_code == 502
    st.Coupon.delete.assert_called_once_with("coup_1")
    assert db.query(models.DiscountCode).filter_by(code="WILLFAIL").first() is None


def test_promo_api_shape_falls_back_for_older_stripe_api(db):
    st = _fake_stripe()
    calls = []

    def create(**kw):
        calls.append(kw)
        if "promotion" in kw:
            raise RuntimeError("Received unknown parameter: promotion")
        return MagicMock(id="promo_old")

    st.PromotionCode.create.side_effect = create
    data = MagicMock(code="x1", percent_off=10, amount_off_cents=None, duration="once",
                     duration_months=None, max_redemptions=None, expires_at=None)
    assert discounts.create_stripe_objects(st, data) == ("coup_1", "promo_old")
    assert "promotion" in calls[0] and calls[1]["coupon"] == "coup_1"


def test_toggle_stripe_code_syncs_to_stripe(db):
    st = _fake_stripe()
    _login(_user(db, admin=True))
    with patch("app.routers.discounts._stripe", return_value=st):
        cid = client.post("/admin/discount-codes", json={"code": "TOGGLE1", "kind": "stripe", "percent_off": 10}).json()["id"]
        r = client.post(f"/admin/discount-codes/{cid}/active", json={"active": False})
    assert r.json()["active"] is False
    st.PromotionCode.modify.assert_called_once_with("promo_1", active=False)


def _stripe_code(db, admin):
    st = _fake_stripe()
    _login(admin)
    with patch("app.routers.discounts._stripe", return_value=st):
        return client.post("/admin/discount-codes", json={"code": f"CK{_n[0]}", "kind": "stripe", "percent_off": 25}).json()


def test_checkout_applies_promo_and_webhook_records_redemption(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "stripe_price_id_pro", "price_1")
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    code = _stripe_code(db, _user(db, admin=True))
    user = _user(db)
    _login(user)
    st = _fake_stripe()
    with patch("app.routers.billing._stripe", return_value=st):
        r = client.post("/billing/subscribe", json={"code": code["code"].lower()})
    assert r.status_code == 200 and r.json()["checkout_url"] == "https://checkout.example/s"
    kw = st.checkout.Session.create.call_args.kwargs
    assert kw["discounts"] == [{"promotion_code": "promo_1"}]
    assert kw["metadata"]["discount_code_id"] == str(code["id"])
    # Not redeemed yet: only checkout completion counts.
    assert db.query(models.DiscountRedemption).filter_by(user_id=user.id).count() == 0

    db.refresh(user)
    event = {"type": "checkout.session.completed", "data": {"object": {
        "customer": user.stripe_customer_id, "subscription": "sub_1",
        "metadata": {"discount_code_id": str(code["id"]), "user_id": str(user.id)},
    }}}
    with patch("app.routers.billing._stripe", return_value=st):
        assert client.post("/billing/webhook", content=__import__("json").dumps(event)).status_code == 200
        assert client.post("/billing/webhook", content=__import__("json").dumps(event)).status_code == 200  # retry is harmless
    assert db.query(models.DiscountRedemption).filter_by(user_id=user.id).count() == 1


def test_subscribe_without_code_unchanged_and_wrong_kind_rejected(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "stripe_price_id_pro", "price_1")
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")
    free_code = _admin_create(_user(db, admin=True)).json()["code"]
    user = _user(db)
    _login(user)
    st = _fake_stripe()
    with patch("app.routers.billing._stripe", return_value=st):
        assert client.post("/billing/subscribe").status_code == 200
        assert "discounts" not in st.checkout.Session.create.call_args.kwargs
        # a free-days code can't be used at checkout; it's redeemed separately
        assert client.post("/billing/subscribe", json={"code": free_code}).status_code == 400


def test_stripe_rejecting_the_discount_gives_a_friendly_error(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "stripe_price_id_pro", "price_1")
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")
    code = _stripe_code(db, _user(db, admin=True))
    _login(_user(db))
    st = _fake_stripe()
    st.checkout.Session.create.side_effect = RuntimeError("promotion code max redemptions reached")
    with patch("app.routers.billing._stripe", return_value=st):
        r = client.post("/billing/subscribe", json={"code": code["code"]})
    assert r.status_code == 400 and r.json()["detail"] == discounts.INVALID


def test_check_code_is_rate_limited(db):
    _login(_user(db))
    codes = [client.post("/billing/check-code", json={"code": "x"}).status_code for _ in range(31)]
    assert codes[:30] == [400] * 30 and codes[30] == 429
