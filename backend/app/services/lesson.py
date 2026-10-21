"""A lesson with a shape.

For learning sessions the coach states two to four goals for the session, teaches
them in order, checks understanding before moving on, and recaps at the end. The
goals and which ones are done are kept on the session so the page can show them
as a checklist. The coach reports progress with small hidden markers
([[plan]] at the start and [[covered:N]] in replies); they are removed before the
text is saved, and if the model leaves them out the lesson simply has no
checklist. Role-play sessions (interview, negotiation) and the resume review
have no lesson.
"""
import json
import re

LESSON_TYPES = ("drill", "walkthrough", "upskill", "leadership")
MAX_GOALS = 4

_PLAN = re.compile(r"\[\[plan\]\](.*?)\[\[/plan\]\]", re.DOTALL | re.IGNORECASE)
_PLAN_OPEN = re.compile(r"\[\[plan\]\](?!.*\[\[/plan\]\]).*\Z", re.DOTALL | re.IGNORECASE)
_COVERED = re.compile(r"\[\[covered:\s*(\d{1,2})\s*\]\]", re.IGNORECASE)

START_NOTE = """LESSON PLAN: this is a learning session, so give it a shape like a good
class. Decide 2 to 4 short goals for today (each under 10 words, in the order
you will teach them) and put them FIRST in your reply as
[[plan]]["goal one","goal two","goal three"][[/plan]] (valid JSON list; the app
hides this and shows it as a checklist). Then, in your opening words, name what
you will cover in ONE short sentence ("Today we'll cover X, then Y.") before your
first question or exercise."""


def block(plan: dict | None) -> str:
    if not plan or not plan.get("goals"):
        return ""
    goals = plan["goals"]
    covered = set(plan.get("covered") or [])
    lines = "\n".join(f"{i + 1}. {g}" + ("  (done)" if i + 1 in covered else "") for i, g in enumerate(goals))
    return f"""LESSON PLAN FOR THIS SESSION (what you told the person you would cover):
{lines}

Teach the goals in order, one at a time. Before you move on from a goal, check understanding with ONE short question: ask them to explain it back in their own words or try a tiny example, then judge their answer honestly. When they have shown they have it, add [[covered:N]] (N = the goal number) anywhere in that reply (the app hides it) and move to the next goal. If they are not there yet, teach it differently and do not mark it. When every goal is covered, give a two-sentence recap and tell them they can end the session for feedback and homework."""


def extract_plan(text: str) -> tuple[str, list[str] | None]:
    """(text without the plan block, the goals when they parse)."""
    goals = None
    m = _PLAN.search(text or "")
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, list):
                cleaned = [re.sub(r"\s+", " ", str(g)).strip()[:80] for g in data if str(g).strip()]
                goals = cleaned[:MAX_GOALS] if len(cleaned) >= 2 else None
        except Exception:
            goals = None
    clean = _PLAN_OPEN.sub("", _PLAN.sub("", text or "")).strip()
    return clean, goals


def extract_covered(text: str, n_goals: int) -> tuple[str, set[int]]:
    """(text without progress markers, the goal numbers that were marked done)."""
    done = {int(n) for n in _COVERED.findall(text or "") if 1 <= int(n) <= n_goals}
    return re.sub(r"[ \t]{2,}", " ", _COVERED.sub("", text or "")).strip(), done


def dump(goals: list[str], covered=()) -> str:
    return json.dumps({"goals": goals, "covered": sorted(set(covered))})
