"""Tests for the Career Coach's teaching styles and diagrams.

Covers the diagram pipeline (validate/clip at write time, resolve at read
time, never trust model output), the style prompt selection, and the
endpoints' handling of a session-level learning style plus one-off
"explain it differently" overrides. Model calls are monkeypatched.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import visuals

client = TestClient(app)
SVC = "app.routers.career_coach.career_coach_service"
_n = [0]

FLOW = {"kind": "flow", "title": "Join order", "steps": [{"label": "FROM"}, {"label": "JOIN", "detail": "match rows"}]}


def block(d):
    return f"[[visual]]{json.dumps(d)}[[/visual]]"


# ---- visuals service -------------------------------------------------------

def test_valid_diagram_roundtrips_and_is_removed_from_text():
    text = visuals.sanitize(f"Look at this. {block(FLOW)} Then try it.")
    clean, v = visuals.extract(text)
    assert v.kind == "flow" and [s.label for s in v.steps] == ["FROM", "JOIN"]
    assert "[[" not in clean and "Look at this." in clean and "Then try it." in clean


@pytest.mark.parametrize("bad", [
    "{not json",
    json.dumps({"kind": "flow", "steps": [{"label": "only one"}]}),
    json.dumps({"kind": "compare", "columns": ["A"], "rows": []}),
    json.dumps({"kind": "map", "center": "x", "branches": []}),
    json.dumps({"kind": "pie", "steps": [{"label": "a"}, {"label": "b"}]}),
    json.dumps([1, 2, 3]),
])
def test_invalid_diagrams_are_dropped_but_text_survives(bad):
    out = visuals.sanitize(f"Explained in words. [[visual]]{bad}[[/visual]]")
    assert out == "Explained in words."
    assert visuals.extract(out)[1] is None


def test_only_first_valid_diagram_is_kept():
    second = {**FLOW, "title": "second"}
    out = visuals.sanitize(f"{block(FLOW)} and {block(second)}")
    assert out.count("[[visual]]") == 1 and "Join order" in out


def test_oversized_diagrams_are_clipped_not_rejected():
    big = {"kind": "flow", "title": "t" * 500,
           "steps": [{"label": f"s{i}", "detail": "d" * 900} for i in range(20)]}
    v = visuals.extract(visuals.sanitize(block(big)))[1]
    assert len(v.steps) == 8 and len(v.title) == 120 and len(v.steps[0].detail) == 240


def test_markup_in_labels_stays_plain_text_data():
    d = {"kind": "map", "center": "<script>alert(1)</script>", "branches": [{"label": "b", "items": ["<img src=x>"]}]}
    v = visuals.extract(visuals.sanitize(block(d)))[1]
    assert v.center == "<script>alert(1)</script>"  # kept as inert text; React renders it escaped


def test_compare_and_map_validate():
    cmp_ = {"kind": "compare", "columns": ["SQL", "NoSQL"], "rows": [{"label": "Schema", "cells": ["fixed", "flexible"]}]}
    mp = {"kind": "map", "center": "Joins", "branches": [{"label": "Types", "items": ["inner", "left"]}]}
    assert visuals.extract(visuals.sanitize(block(cmp_)))[1].kind == "compare"
    assert visuals.extract(visuals.sanitize(block(mp)))[1].kind == "map"


# ---- style prompts ---------------------------------------------------------

def test_style_prompts():
    auto = visuals.teaching_block("auto", None, "drill")
    assert "[[visual]]" in auto and "Explain it differently" in auto
    assert "[[visual]]" in visuals.teaching_block("visual", None, "drill")
    hands_on = visuals.teaching_block("handson", None, "drill")
    assert "HANDS-ON" in hands_on and "[[visual]]" not in hands_on
    # a one-off request beats the session default and says so
    once = visuals.teaching_block("handson", "visual", "drill")
    assert "VISUAL" in once and "THIS reply only" in once and "[[visual]]" in once
    assert "ignore all teaching styles" in visuals.teaching_block("visual", None, "interview")
    assert "ignore all teaching styles" not in visuals.teaching_block("visual", None, "drill")


# ---- endpoints -------------------------------------------------------------

@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _user(db):
    _n[0] += 1
    u = models.User(email=f"style{_n[0]}@x.com", hashed_password="x", full_name="T", resume_text="Analyst.")
    db.add(u)
    db.commit()
    db.refresh(u)
    app.dependency_overrides[get_current_user] = lambda: u
    return u


def _start(style=None, opening="Hi."):
    body = {"session_type": "drill", "target_role": "Data Analyst"}
    if style:
        body["learning_style"] = style
    seen = {}

    def fake(*a, learning_style=None, **k):
        seen["style"] = learning_style
        return {"topic": "Joins", "opening_message": opening}

    with patch(f"{SVC}.start_session", side_effect=fake):
        return client.post("/career-coach/sessions", json=body), seen


def test_learning_style_is_stored_returned_and_passed_to_coach(db):
    _user(db)
    resp, seen = _start("visual")
    assert resp.status_code == 200 and resp.json()["session"]["learning_style"] == "visual"
    assert seen["style"] == "visual"
    assert _start()[0].json()["session"]["learning_style"] == "auto"  # default
    assert _start("bogus")[0].status_code == 422


def test_opening_message_can_carry_a_diagram(db):
    _user(db)
    resp, _ = _start("visual", opening=f"Here is the picture. {block(FLOW)}")
    opening = resp.json()["opening_message"]
    assert opening["visual"]["kind"] == "flow" and "[[" not in opening["content"]


def test_reply_returns_diagram_and_passes_styles(db):
    _user(db)
    sid = _start("story")[0].json()["session"]["id"]
    seen = {}

    def fake_reply(*a, learning_style=None, style=None, **k):
        seen.update(learning_style=learning_style, style=style)
        return f"Think of a funnel. {block(FLOW)}"

    with patch(f"{SVC}.reply", side_effect=fake_reply):
        resp = client.post(f"/career-coach/sessions/{sid}/messages",
                           json={"message": "explain differently", "style": "visual"})
    assert resp.status_code == 200
    assert seen == {"learning_style": "story", "style": "visual"}
    body = resp.json()
    assert body["visual"]["title"] == "Join order" and body["content"] == "Think of a funnel."
    # history endpoint resolves the stored diagram the same way
    history = client.get(f"/career-coach/sessions/{sid}/messages").json()
    assert history[-1]["visual"]["kind"] == "flow"


def test_garbage_diagram_from_model_is_never_stored(db):
    _user(db)
    sid = _start()[0].json()["session"]["id"]
    with patch(f"{SVC}.reply", return_value="Plain answer. [[visual]]{oops}[[/visual]]"):
        resp = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "hi"})
    assert resp.json()["visual"] is None and resp.json()["content"] == "Plain answer."
    saved = db.query(models.CareerCoachMessage).filter_by(session_id=sid, role="assistant").order_by(models.CareerCoachMessage.id.desc()).first()
    assert "[[visual]]" not in saved.content


def test_message_style_override_is_validated(db):
    _user(db)
    sid = _start()[0].json()["session"]["id"]
    with patch(f"{SVC}.reply", return_value="ok"):
        assert client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "x", "style": "auto"}).status_code == 422
        assert client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "x"}).status_code == 200
