"""Every metered action must have a cost estimate, or Admin shows it as free."""
from app.services import admin_stats, usage


def test_every_metered_action_has_a_cost_estimate():
    metered = set(usage.FREE_LIMITS) | set(usage.PRO_LIMITS)
    missing = sorted(a for a in metered if admin_stats.ESTIMATED_COST_PER_ACTION.get(a, 0) <= 0)
    assert not missing, f"Add a cost estimate in admin_stats.ESTIMATED_COST_PER_ACTION for: {missing}"


def test_estimate_cost_multiplies_and_rounds():
    assert admin_stats.estimate_cost("career_coach_message", 100) == 3.0
    assert admin_stats.estimate_cost("unknown_action", 5) == 0.0
