"""Diagrams for visual learners.

The coach may teach with one small diagram per reply. It writes the
diagram as JSON between [[visual]] ... [[/visual]] markers; this module
validates it, clips it to sane sizes, and the router hands the frontend a
typed `visual` object to draw. The model only ever supplies data -- never
HTML, SVG or URLs -- so there is nothing to inject, and a malformed or
oversized diagram is simply dropped (the coach is instructed to always
explain in words too, so the reply still stands on its own).

Same shape as services/library.py: sanitize at write time so garbage is
never stored, resolve at read time.
"""
import json
import math
import re

from pydantic import ValidationError

from app import schemas

BLOCK_RE = re.compile(r"\[\[visual\]\](.*?)\[\[/visual\]\]", re.DOTALL | re.IGNORECASE)
# A reply that hit its length limit mid-picture leaves an opening marker with
# no end. That half-written code is dropped, never shown to the person.
_OPEN_TAIL_RE = re.compile(r"\[\[visual\]\](?!.*\[\[/visual\]\]).*\Z", re.DOTALL | re.IGNORECASE)

_STR_LIMITS = {"label": 80, "detail": 240, "title": 120, "center": 80}


def _clip_str(v, n: int) -> str:
    return str(v).strip()[:n] if v is not None else ""


# An icon is one small emoji picture. Anything with letters, digits or
# punctuation in it is dropped, so it can only ever be a picture.
_ICON_OK = re.compile(r"^[\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u231a-\u23ff\u24c2\u25aa-\u25fe\u2600-\u27bf\u2b00-\u2bff\U0001F000-\U0001FAFF\uFE0F\u200D\u20E3]{1,8}$")


def _icon(v) -> str:
    s = str(v).strip() if v is not None else ""
    return s if s and _ICON_OK.match(s) else ""


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and 0 <= f <= 1e12 else None


def _clean(data: dict) -> dict:
    """Leniently shrinks a model-produced dict into the schema's bounds
    (a diagram with nine steps should show eight, not vanish)."""
    out = {"kind": str(data.get("kind", "")).strip().lower(), "title": _clip_str(data.get("title"), 120)}
    out["steps"] = [
        {"label": _clip_str(s.get("label"), 80), "detail": _clip_str(s.get("detail"), 240), "icon": _icon(s.get("icon"))}
        for s in (data.get("steps") or [])[:8] if isinstance(s, dict) and s.get("label")
    ]
    out["columns"] = [_clip_str(c, 40) for c in (data.get("columns") or [])[:4]]
    out["rows"] = [
        {"label": _clip_str(r.get("label"), 80), "cells": [_clip_str(c, 120) for c in (r.get("cells") or [])[:4]]}
        for r in (data.get("rows") or [])[:8] if isinstance(r, dict) and r.get("label")
    ]
    out["center"] = _clip_str(data.get("center"), 80)
    out["branches"] = [
        {"label": _clip_str(b.get("label"), 80), "items": [_clip_str(i, 80) for i in (b.get("items") or [])[:5]],
         "icon": _icon(b.get("icon"))}
        for b in (data.get("branches") or [])[:6] if isinstance(b, dict) and b.get("label")
    ]
    out["axes"] = [_clip_str(a, 40) for a in (data.get("axes") or [])[:2]]
    out["quadrants"] = [
        {"label": _clip_str(q.get("label"), 80), "items": [_clip_str(i, 80) for i in (q.get("items") or [])[:4]],
         "icon": _icon(q.get("icon"))}
        for q in (data.get("quadrants") or [])[:4] if isinstance(q, dict) and q.get("label")
    ]
    bars = []
    for b in (data.get("bars") or [])[:8]:
        if isinstance(b, dict) and b.get("label") and _num(b.get("value")) is not None:
            bars.append({"label": _clip_str(b.get("label"), 80), "value": _num(b.get("value")), "icon": _icon(b.get("icon"))})
    out["bars"] = bars
    out["unit"] = _clip_str(data.get("unit"), 20)
    return out


def _parse(raw: str) -> schemas.VisualOut | None:
    try:
        data = json.loads(raw.strip())
        if not isinstance(data, dict):
            return None
        v = schemas.VisualOut(**_clean(data))
    except (ValueError, ValidationError, AttributeError, TypeError):
        return None
    # A diagram with nothing in it for its kind isn't worth drawing.
    if v.kind in ("flow", "cycle") and len(v.steps) < 2:
        return None
    if v.kind == "layers" and len(v.steps) < 2:
        return None
    if v.kind == "matrix" and (len(v.axes) < 2 or len(v.quadrants) != 4):
        return None
    if v.kind == "chart" and (len(v.bars) < 2 or max(b.value for b in v.bars) <= 0):
        return None
    if v.kind == "compare" and (not v.columns or not v.rows):
        return None
    if v.kind == "map" and (not v.center or not v.branches):
        return None
    return v


def sanitize(text: str) -> str:
    """Write-time: keeps at most the FIRST valid diagram (re-serialized
    from the validated form) and removes every other / invalid block."""
    kept = {"done": False}

    def swap(m: re.Match) -> str:
        if kept["done"]:
            return ""
        v = _parse(m.group(1))
        if not v:
            return ""
        kept["done"] = True
        return "[[visual]]" + json.dumps(v.model_dump(), ensure_ascii=False) + "[[/visual]]"

    return _OPEN_TAIL_RE.sub("", BLOCK_RE.sub(swap, text)).strip()


def extract(text: str) -> tuple[str, schemas.VisualOut | None]:
    """Read-time: (text with diagram blocks removed, first valid diagram)."""
    visual = None
    for m in BLOCK_RE.finditer(text):
        visual = _parse(m.group(1))
        if visual:
            break
    clean = _OPEN_TAIL_RE.sub("", BLOCK_RE.sub("", text))
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, visual


_FORMAT = """DIAGRAMS AND PICTURES: you can draw ONE small diagram per reply by writing
it as JSON between the markers [[visual]] and [[/visual]] (the app draws it).
THE WHITEBOARD: the diagram appears on a whiteboard and is drawn out step by
step, piece by piece, as the person reads, like a teacher drawing at the
board in a live class. So talk like that teacher: introduce it in a few words
("let me sketch this out"), point at the parts as they appear ("the second
box is where..."), and do not repeat every box in words, because the board
carries the structure. Your words explain WHY each part matters.
Use it when a picture genuinely helps -- a process, a loop, a comparison,
how parts relate, a priority grid, a hierarchy, or a few numbers -- and
ALWAYS also explain the idea in words, because the diagram may not display
for everyone. Write the [[visual]] block FIRST in your reply, before the
words, and keep it compact, so a long reply can never cut it off. Formats (pick the one that fits):
  [[visual]]{"kind":"flow","title":"...","steps":[{"label":"short step","detail":"one line","icon":"🔍"}, ...]}[[/visual]]
  [[visual]]{"kind":"cycle","title":"...","steps":[{"label":"step that leads to the next","detail":"one line"}, ...]}[[/visual]]
  [[visual]]{"kind":"compare","title":"...","columns":["A","B"],"rows":[{"label":"row","cells":["for A","for B"]}, ...]}[[/visual]]
  [[visual]]{"kind":"map","title":"...","center":"main idea","branches":[{"label":"group","items":["short","short"],"icon":"🛡️"}, ...]}[[/visual]]
  [[visual]]{"kind":"matrix","title":"...","axes":["horizontal axis","vertical axis"],"quadrants":[{"label":"top-left","items":["short"]},{"label":"top-right","items":[]},{"label":"bottom-left","items":[]},{"label":"bottom-right","items":[]}]}[[/visual]]
  [[visual]]{"kind":"layers","title":"...","steps":[{"label":"top layer","detail":"one line"}, ...]}[[/visual]]
  [[visual]]{"kind":"chart","title":"...","unit":"%","bars":[{"label":"item","value":42}, ...]}[[/visual]]
Meanings: flow = ordered steps. cycle = steps that loop back to the first.
matrix = a 2x2 grid; quadrants go top-left, top-right, bottom-left,
bottom-right, and the axes are [horizontal, vertical]. layers = a stack or
pyramid, written top to bottom. chart = horizontal bars of numbers.
"icon" is optional: ONE emoji that pictures the item (a magnifier for
"research", a shield for "security"). Use it only where it helps; never
text in it.
CHARTS: never present invented numbers as facts. Use real, well-known
figures only if you are sure, otherwise make the title say "Example
numbers" so no one mistakes them for data.
Limits: flow, cycle and layers up to 8 steps; compare up to 4 columns and 8
rows; map up to 6 branches of up to 5 items; matrix exactly 4 quadrants of
up to 4 items; chart up to 8 bars. Keep every label under ~8 words. Valid
JSON only, on a single block, no markdown fences around it."""

_STYLES = {
    "visual": "TEACHING STYLE -- VISUAL: this person learns best by seeing. Lead with a diagram whenever the idea has a process, structure, comparison, or relationships, then walk through it in words. Use spatial language (\"first box...\") and keep text short.",
    "handson": "TEACHING STYLE -- HANDS-ON: this person learns by doing. Don't explain first. Give a small, concrete exercise or mini-task they can attempt right now -- on a real tool from the field when there is one (see the real-tools guidance) -- wait for their try, then explain based on what they did.",
    "story": "TEACHING STYLE -- STORIES & ANALOGIES: this person learns through meaning. Anchor the idea in a vivid real-world analogy or a short realistic workplace scenario, then connect it back to the actual concept. Keep the analogy accurate -- say where it breaks down.",
    "stepbystep": "TEACHING STYLE -- STEP BY STEP: this person learns through worked examples. Show a small example solved one step at a time, in plain sentences (\"First...\", \"Next...\") with the reasoning for each, not as a labeled STEP 1 / STEP 2 template. Then give them a similar one to try. One idea per step.",
}

_AUTO = """TEACHING STYLE -- ADAPTIVE: teach the way that fits the idea and the
person. Go to the whiteboard whenever the idea is a process, a loop, a
comparison, a hierarchy, how parts connect, or a set of numbers: for a new
idea like that, draw it. Do not draw for a quick answer, a yes/no, or advice
that is just words, and not in every reply -- a good teacher uses the board
when it helps. If they seem stuck or confused, change approach rather than
repeating yourself -- try a diagram, an analogy, a worked example, or a
small exercise. Occasionally, not every message, mention they can tap
"Explain it differently" to get a visual, a step-by-step, an analogy, or a
hands-on try."""


_KIND_NAMES = {
    "flow": "a process flow (kind \"flow\")", "cycle": "a cycle that loops back (kind \"cycle\")",
    "compare": "a comparison table (kind \"compare\")", "map": "a concept map (kind \"map\")",
    "matrix": "a 2x2 grid (kind \"matrix\")", "layers": "a layered stack or pyramid (kind \"layers\")",
    "chart": "a bar chart (kind \"chart\")",
}

_OPTIONAL_PICTURE = ("PICTURES ARE AVAILABLE: this teaching style does not depend on diagrams, but if a "
                     "small picture would clearly help the idea land, you may draw one.")


def teaching_block(session_style: str, one_off_style: str | None, session_type: str, visual_kind: str | None = None) -> str:
    """The teaching-style section of a coach prompt. A one-off style (the
    person tapped 'Explain it differently') beats the session default. A
    visual_kind (they picked "Draw it as...") names the picture to draw."""
    style = one_off_style or session_style or "auto"
    body = _STYLES.get(style, _AUTO)
    if style in ("auto", "visual") or one_off_style == "visual":
        out = f"{body}\n\n{_FORMAT}"
    else:
        # Hands-on, story and step-by-step keep their own approach, but the
        # coach may still add a picture when it clearly helps.
        out = f"{body}\n\n{_OPTIONAL_PICTURE}\n\n{_FORMAT}"
    if visual_kind in _KIND_NAMES:
        out += (f"\n\nTHE PERSON CHOSE THE PICTURE: draw {_KIND_NAMES[visual_kind]} for this reply, "
                "built from what you have been teaching, and walk through it in words.")
    if one_off_style:
        out = ("For THIS reply only, re-teach what you just covered in this different way "
               "(the person asked for another way to understand it).\n\n" + out)
    if session_type in ("interview", "negotiation"):
        out += ("\n\nROLE-PLAY NOTE: while you are in character (the interviewer or the recruiter), "
                "ignore all teaching styles and diagrams. They apply only if you step out "
                "of the role-play to teach.")
    return out
