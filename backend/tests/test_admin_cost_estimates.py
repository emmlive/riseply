"""Every metered action must have a cost estimate, or Admin shows it as free."""
from app.services import admin_stats, usage


def test_every_metered_action_has_a_cost_estimate():
    metered = set(usage.FREE_LIMITS) | set(usage.PRO_LIMITS)
    missing = sorted(a for a in metered if admin_stats.ESTIMATED_COST_PER_ACTION.get(a, 0) <= 0)
    assert not missing, f"Add a cost estimate in admin_stats.ESTIMATED_COST_PER_ACTION for: {missing}"


def test_estimate_cost_multiplies_and_rounds():
    assert admin_stats.estimate_cost("career_coach_message", 100) == 3.0
    assert admin_stats.estimate_cost("unknown_action", 5) == 0.0


def test_net_revenue_after_stripe_fee():
    assert admin_stats.net_revenue_per_pro(9.99) == 9.4


def test_cost_per_user_splits_pro_and_free_and_skips_admins():
    import uuid
    import app.main  # noqa: F401  (creates the tables)
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    period = "2031-" + str(1 + uuid.uuid4().int % 9).zfill(2)  # a month no other test writes to
    mk = lambda **kw: models.User(email=f"c{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", **kw)
    pro_heavy = mk(subscription_tier="pro", subscription_status="active")
    pro_light = mk(subscription_tier="pro", subscription_status="active")
    free = mk()
    admin = mk(is_admin=True, subscription_tier="pro", subscription_status="active")
    db.add_all([pro_heavy, pro_light, free, admin]); db.commit()
    for u, action, n in [(pro_heavy, "career_coach_message", 400), (pro_light, "match", 10), (free, "match", 5), (admin, "career_coach_message", 900)]:
        db.add(models.UsageLog(user_id=u.id, period=period, action=action, count=n))
    db.commit()
    out = admin_stats.cost_per_user(db, period, 9.99)
    ids = {h["user_id"] for h in out["heaviest"]}
    assert admin.id not in ids and out["heaviest"][0]["user_id"] == pro_heavy.id
    assert out["heaviest"][0]["cost_usd"] == 12.0 and out["heaviest"][0]["top_action"] == "career_coach_message"
    pro = out["pro"]
    assert pro["max_cost_usd"] == 12.0 and pro["net_revenue_per_user_usd"] == 9.4
    assert pro["over_revenue_users"] >= 1 and pro["top_actions"][0]["action"] == "career_coach_message"
    assert out["free"]["active_users"] >= 1
    db.close()
