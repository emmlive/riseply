"""The coach's picture kinds: cycle, 2x2 matrix, layers, bar chart, and the
emoji icons -- validated, clipped, and safe (data only, never markup)."""
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import visuals


def block(d):
    return "[[visual]]" + json.dumps(d) + "[[/visual]]"


def test_cycle_and_layers_need_two_steps_and_keep_icons():
    steps = [{"label": "Plan", "detail": "decide", "icon": "📝"}, {"label": "Do", "icon": "🛠️"}]
    for kind in ("cycle", "layers"):
        text, v = visuals.extract("Words. " + block({"kind": kind, "title": "T", "steps": steps}))
        assert v and v.kind == kind and [s.icon for s in v.steps] == ["📝", "🛠️"] and "[[visual]]" not in text
        assert visuals.extract(block({"kind": kind, "steps": steps[:1]}))[1] is None


def test_matrix_needs_two_axes_and_exactly_four_quadrants():
    quads = [{"label": q, "items": ["a", "b"]} for q in ("Do first", "Plan", "Delegate", "Drop")]
    v = visuals.extract(block({"kind": "matrix", "axes": ["Urgent", "Important"], "quadrants": quads}))[1]
    assert v and v.axes == ["Urgent", "Important"] and [q.label for q in v.quadrants] == ["Do first", "Plan", "Delegate", "Drop"]
    assert visuals.extract(block({"kind": "matrix", "axes": ["Urgent", "Important"], "quadrants": quads[:3]}))[1] is None
    assert visuals.extract(block({"kind": "matrix", "axes": ["Urgent"], "quadrants": quads}))[1] is None


def test_chart_keeps_only_real_numbers_and_needs_two_bars():
    v = visuals.extract(block({"kind": "chart", "title": "Example numbers", "unit": "%", "bars": [
        {"label": "A", "value": 40}, {"label": "B", "value": "25.5"}, {"label": "bad", "value": "lots"},
        {"label": "neg", "value": -3}, {"label": "inf", "value": 1e999},
    ]}))[1]
    assert v and [(b.label, b.value) for b in v.bars] == [("A", 40.0), ("B", 25.5)] and v.unit == "%"
    assert visuals.extract(block({"kind": "chart", "bars": [{"label": "A", "value": 1}]}))[1] is None
    assert visuals.extract(block({"kind": "chart", "bars": [{"label": "A", "value": 0}, {"label": "B", "value": 0}]}))[1] is None


def test_icons_can_only_be_pictures():
    text = block({"kind": "flow", "steps": [
        {"label": "One", "icon": "🔍"}, {"label": "Two", "icon": "<script>alert(1)</script>"},
        {"label": "Three", "icon": "Step 3"}, {"label": "Four", "icon": "A"},
    ]})
    v = visuals.extract(text)[1]
    assert [s.icon for s in v.steps] == ["🔍", "", "", ""]


def test_unknown_kinds_are_still_dropped():
    assert visuals.extract(block({"kind": "pie", "bars": [{"label": "a", "value": 1}, {"label": "b", "value": 2}]}))[1] is None


def test_chosen_picture_and_optional_pictures_reach_the_prompt():
    out = visuals.teaching_block("auto", "visual", "drill", "matrix")
    assert "THE PERSON CHOSE THE PICTURE" in out and 'kind "matrix"' in out
    assert "THE PERSON CHOSE" not in visuals.teaching_block("auto", "visual", "drill", None)
    assert "THE PERSON CHOSE" not in visuals.teaching_block("auto", "visual", "drill", "pie")
    for kind in ("cycle", "matrix", "layers", "chart"):
        assert f'"kind":"{kind}"' in visuals.teaching_block("visual", None, "drill")


@pytest.fixture()
def client():
    db = SessionLocal()
    user = models.User(email=f"vk-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="Engineer.")
    db.add(user); db.commit(); db.refresh(user)
    sess = models.CareerCoachSession(user_id=user.id, session_type="drill", target_role="Analyst", topic="Prioritising", status="in_progress")
    db.add(sess); db.commit(); db.refresh(sess)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), sess
    app.dependency_overrides.clear()
    db.close()


def test_draw_it_as_passes_the_kind_to_the_coach_and_returns_the_picture(client):
    c, sess = client
    quads = [{"label": q} for q in ("Do first", "Plan", "Delegate", "Drop")]
    reply = "Here is the grid. " + block({"kind": "matrix", "axes": ["Urgent", "Important"], "quadrants": quads})
    with patch("app.services.career_coach.reply", return_value=reply) as coach:
        r = c.post(f"/career-coach/sessions/{sess.id}/messages",
                   json={"message": "Draw it as a grid", "style": "visual", "visual_kind": "matrix"})
    assert r.status_code == 200, r.text
    assert coach.call_args.kwargs["visual_kind"] == "matrix"
    body = r.json()
    assert body["visual"]["kind"] == "matrix" and len(body["visual"]["quadrants"]) == 4
    assert "[[visual]]" not in body["content"]


def test_bad_visual_kind_is_rejected(client):
    c, sess = client
    r = c.post(f"/career-coach/sessions/{sess.id}/messages", json={"message": "hi", "visual_kind": "pie"})
    assert r.status_code == 422
