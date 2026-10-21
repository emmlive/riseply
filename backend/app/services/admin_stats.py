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
    "task_guide": 0.08,  # one long answer (plan plus templates), about 5k output tokens
    "coach_video": 0.0001,  # a YouTube search is quota, not dollars; kept above zero so it shows up
}


def estimate_cost(action: str, count: int) -> float:
    per_call = ESTIMATED_COST_PER_ACTION.get(action, 0.0)
    return round(per_call * count, 2)
