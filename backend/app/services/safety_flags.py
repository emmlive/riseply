"""
Lightweight, keyword-based safety flagging for Job Buddy messages.

This is deliberately coarse: a cheap pattern match, not a classifier, and
it never blocks, alters, or auto-responds to anything. Its only effect is
setting `flagged`/`flag_reason` on a message row so it surfaces in the
admin trust & safety queue for a human to actually look at. False
positives are fine and expected -- silently missing a message that needed
a look is the worse failure mode here.

Deliberately narrow in scope to what a human admin can act on: personal
safety risk, and content that may violate the "no harassing, discriminatory,
or illegal content" acceptable-use terms. General product complaints or
negative sentiment about a job are not flagged -- that's just normal
onboarding-coaching conversation, not a safety signal.
"""

CATEGORIES: dict[str, list[str]] = {
    "possible self-harm or crisis": [
        "kill myself", "suicide", "want to die", "end my life", "self harm",
        "self-harm", "hurting myself", "don't want to be alive", "no reason to live",
    ],
    "possible harassment / discrimination reported or generated": [
        "sexually harassed", "sexual harassment", "racial slur", "hate speech",
        "discriminated against", "groped", "assaulted",
    ],
    "possible workplace safety / illegal activity": [
        "unsafe working conditions", "asked me to falsify", "asked me to lie to",
        "threatened me", "retaliat",
    ],
}


def scan(text: str) -> str:
    """Returns a short category label if `text` matches a flagged pattern,
    or "" if nothing matched. Case-insensitive substring match -- crude on
    purpose, kept easy to extend without adding a model dependency here."""
    if not text:
        return ""
    lowered = text.lower()
    for category, phrases in CATEGORIES.items():
        for phrase in phrases:
            if phrase in lowered:
                return category
    return ""
