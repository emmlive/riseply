"""
Cost estimates per metered action, at Claude Sonnet pricing ($3/M input,
$15/M output tokens) based on typical prompt/output sizes for each call.
These are estimates, not exact -- actual token counts vary with resume
length and job description length. Good enough for a rough "what is this
costing us" signal, not for precise billing reconciliation.
"""

ESTIMATED_COST_PER_ACTION = {
    "match": 0.008,
    "tailor_resume": 0.019,
    "interview_prep": 0.020,
    "onboarding_plan": 0.025,
    "job_buddy_message": 0.010,
    "org_ask": 0.012,
    "coaching_message": 0.010,
    # The Career Coach re-sends its long instructions, the person's context
    # and the conversation on every message, so it is the costliest per call.
    "career_coach_message": 0.030,
    "skill_gap": 0.030,
    "fit_score": 0.015,
    "networking": 0.020,
    "company_brief": 0.020,
    "career_path": 0.025,
    "course": 0.05,  # one syllabus, about 2.5k output tokens
    "task_guide": 0.12,  # one long answer (plan plus templates), about 7k output tokens
    "coach_video": 0.0001,  # a YouTube search is quota, not dollars; kept above zero so it shows up
}


def estimate_cost(action: str, count: int) -> float:
    per_call = ESTIMATED_COST_PER_ACTION.get(action, 0.0)
    return round(per_call * count, 2)


# ---------- cost per user (for the pricing decision) ----------

STRIPE_PERCENT = 0.029
STRIPE_FIXED_USD = 0.30


def net_revenue_per_pro(price_usd: float) -> float:
    """What a monthly Pro payment leaves after Stripe's card fee (about 2.9% + $0.30)."""
    return round(price_usd * (1 - STRIPE_PERCENT) - STRIPE_FIXED_USD, 2)


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _summary(costs: list[float]) -> dict:
    s = sorted(costs)
    n = len(s)
    return {
        "users": n, "total_cost_usd": round(sum(s), 2),
        "avg_cost_usd": round(sum(s) / n, 2) if n else 0.0,
        "median_cost_usd": round(_percentile(s, 0.5), 2),
        "p90_cost_usd": round(_percentile(s, 0.9), 2),
        "max_cost_usd": round(s[-1], 2) if n else 0.0,
    }


def cost_per_user(db, period: str, price_usd: float) -> dict:
    """Estimated AI cost per user for a month, split into paying Pro users and
    everyone else (free and complimentary). Admin accounts are left out: they
    exist for testing and would skew the averages. Costs come from the same
    per-action estimates as the usage card, so they are as rough as those."""
    from app import models

    users = db.query(models.User).filter(models.User.is_admin.is_(False)).all()
    rows = db.query(models.UsageLog.user_id, models.UsageLog.action, models.UsageLog.count).filter_by(period=period).all()
    by_user: dict[int, dict[str, float]] = {}
    for uid, action, count in rows:
        by_user.setdefault(uid, {})[action] = by_user.get(uid, {}).get(action, 0.0) + estimate_cost(action, int(count or 0))

    def total(uid):
        return round(sum(by_user.get(uid, {}).values()), 4)

    pro = [u for u in users if u.subscription_tier == "pro" and u.subscription_status == "active"]
    pro_ids = {u.id for u in pro}
    other = [u for u in users if u.id not in pro_ids]
    pro_costs = [total(u.id) for u in pro]
    net = net_revenue_per_pro(price_usd)

    pro_summary = _summary(pro_costs)
    pro_summary.update({
        "net_revenue_per_user_usd": net,
        "over_revenue_users": sum(1 for c in pro_costs if c > net),
        "avg_margin_pct": round((net - pro_summary["avg_cost_usd"]) / net * 100) if net > 0 and pro else 0,
    })
    feature: dict[str, float] = {}
    for u in pro:
        for a, c in by_user.get(u.id, {}).items():
            feature[a] = feature.get(a, 0.0) + c
    pro_summary["top_actions"] = [{"action": a, "cost_usd": round(c, 2)} for a, c in sorted(feature.items(), key=lambda x: -x[1])[:6]]

    active_other = [total(u.id) for u in other if total(u.id) > 0]
    other_summary = _summary(active_other)
    other_summary["users"] = len(other)
    other_summary["active_users"] = len(active_other)

    heavy = sorted(users, key=lambda u: -total(u.id))[:8]
    heaviest = []
    for u in heavy:
        if total(u.id) <= 0:
            break
        acts = by_user.get(u.id, {})
        heaviest.append({
            "user_id": u.id, "email": u.email, "plan": "pro" if u.id in pro_ids else "free",
            "cost_usd": round(total(u.id), 2), "top_action": max(acts, key=acts.get) if acts else "",
        })
    return {"period": period, "pro": pro_summary, "free": other_summary, "heaviest": heaviest}
