"""A plain heads-up before someone spends an application on a poor fit.
Applying to fewer, closer roles gets more replies than applying to everything."""

WEAK = 45
STRETCH = 65


def fit_note(score: int, status: str) -> str:
    """Empty when the match is good or the application is already past the decision."""
    if status != "pending_approval":
        return ""
    if score < WEAK:
        return ("Low match. This role is far from your resume, so it is unlikely to get a reply. "
                "Look for a closer role before using an application on it.")
    if score < STRETCH:
        return ("Stretch role. Apply only if you can show the missing skills in your own words, "
                "and expect fewer replies than from a close match.")
    return ""
