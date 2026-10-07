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
import re

from pydantic import ValidationError

from app import schemas

BLOCK_RE = re.compile(r"\[\[visual\]\](.*?)\[\[/visual\]\]", re.DOTALL | re.IGNORECASE)

_STR_LIMITS = {"label": 80, "detail": 240, "title": 120, "center": 80}


def _clip_str(v, n: int) -> str:
    return str(v).strip()[:n] if v is not None else ""


def _clean(data: dict) -> dict:
    """Leniently shrinks a model-produced dict into the schema's bounds
    (a diagram with nine steps should show eight, not vanish)."""
    out = {"kind": str(data.get("kind", "")).strip().lower(), "title": _clip_str(data.get("title"), 120)}
    out["steps"] = [
        {"label": _clip_str(s.get("label"), 80), "detail": _clip_str(s.get("detail"), 240)}
        for s in (data.get("steps") or [])[:8] if isinstance(s, dict) and s.get("label")
    ]
    out["columns"] = [_clip_str(c, 40) for c in (data.get("columns") or [])[:4]]
    out["rows"] = [
        {"label": _clip_str(r.get("label"), 80), "cells": [_clip_str(c, 120) for c in (r.get("cells") or [])[:4]]}
        for r in (data.get("rows") or [])[:8] if isinstance(r, dict) and r.get("label")
    ]
    out["center"] = _clip_str(data.get("center"), 80)
    out["branches"] = [
        {"label": _clip_str(b.get("label"), 80), "items": [_clip_str(i, 80) for i in (b.get("items") or [])[:5]]}
        for b in (data.get("branches") or [])[:6] if isinstance(b, dict) and b.get("label")
    ]
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
    if v.kind == "flow" and len(v.steps) < 2:
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

    return BLOCK_RE.sub(swap, text).strip()


def extract(text: str) -> tuple[str, schemas.VisualOut | None]:
    """Read-time: (text with diagram blocks removed, first valid diagram)."""
    visual = None
    for m in BLOCK_RE.finditer(text):
        visual = _parse(m.group(1))
        if visual:
            break
    clean = BLOCK_RE.sub("", text)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, visual


_FORMAT = """DIAGRAMS: you can draw ONE small diagram per reply by writing it as
JSON between the markers [[visual]] and [[/visual]] (the app draws it).
Use it only when a picture genuinely helps (a process, a comparison, how
parts relate) -- and ALWAYS also explain the idea in words, because the
diagram may not display for everyone. Formats (pick one):
  [[visual]]{"kind":"flow","title":"...","steps":[{"label":"short step","detail":"one line"}, ...]}[[/visual]]
  [[visual]]{"kind":"compare","title":"...","columns":["A","B"],"rows":[{"label":"row","cells":["for A","for B"]}, ...]}[[/visual]]
  [[visual]]{"kind":"map","title":"...","center":"main idea","branches":[{"label":"group","items":["short","short"]}, ...]}[[/visual]]
Limits: flow up to 8 steps; compare up to 4 columns and 8 rows; map up to
6 branches of up to 5 items. Keep every label under ~8 words. Valid JSON
only, on a single block, no markdown fences around it."""

_STYLES = {
    "visual": "TEACHING STYLE -- VISUAL: this person learns best by seeing. Lead with a diagram whenever the idea has a process, structure, comparison, or relationships, then walk through it in words. Use spatial language (\"first box...\") and keep text short.",
    "handson": "TEACHING STYLE -- HANDS-ON: this person learns by doing. Don't explain first. Give a small, concrete exercise or mini-task they can attempt right now, wait for their try, then explain based on what they did.",
    "story": "TEACHING STYLE -- STORIES & ANALOGIES: this person learns through meaning. Anchor the idea in a vivid real-world analogy or a short realistic workplace scenario, then connect it back to the actual concept. Keep the analogy accurate -- say where it breaks down.",
    "stepbystep": "TEACHING STYLE -- STEP BY STEP: this person learns through worked examples. Show a small example solved in numbered steps with the reasoning for each, then give them a similar one to try. One idea per step.",
}

_AUTO = """TEACHING STYLE -- ADAPTIVE: teach the way that fits the idea and the
person. If they seem stuck or confused, change approach rather than
repeating yourself -- try a diagram, an analogy, a worked example, or a
small exercise. Occasionally, not every message, mention they can tap
"Explain it differently" to get a visual, a step-by-step, an analogy, or a
hands-on try."""


def teaching_block(session_style: str, one_off_style: str | None, session_type: str) -> str:
    """The teaching-style section of a coach prompt. A one-off style (the
    person tapped 'Explain it differently') beats the session default."""
    style = one_off_style or session_style or "auto"
    body = _STYLES.get(style, _AUTO)
    out = f"{body}\n\n{_FORMAT}" if style in ("auto", "visual") or one_off_style == "visual" else body
    if one_off_style:
        out = ("For THIS reply only, re-teach what you just covered in this different way "
               "(the person asked for another way to understand it).\n\n" + out)
    if session_type == "interview":
        out += ("\n\nMOCK INTERVIEW NOTE: while you are in character as the interviewer, "
                "ignore all teaching styles and diagrams. They apply only if you step out "
                "of the interview to teach.")
    return out
