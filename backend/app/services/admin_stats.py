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
}


def estimate_cost(action: str, count: int) -> float:
    per_call = ESTIMATED_COST_PER_ACTION.get(action, 0.0)
    return round(per_call * count, 2)
