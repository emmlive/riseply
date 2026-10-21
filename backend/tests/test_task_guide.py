"""Task guide: building, saving progress, help, ownership, metering and parsing.
The model call is patched; these cover the plumbing and the validation of what
the model returns."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import usage, task_guide

client = TestClient(app)
_n = [0]
SVC = "app.routers.task_guides.task_guide_service"

GOOD = {
    "title": "Weekly status report", "goal": "A one-page report your manager can read in two minutes.",
    "deliverable": "a one-page report", "why_it_matters": "It drives Monday's meeting.",
    "confirm_first": ["Who reads it?", "What format?"],
    "requirements": [{"item": "Last week's numbers", "why": "To compare"}, "Access to the tracker"],
    "materials": [{"name": "Report template", "purpose": "Skeleton", "template": "# Status\n- [DONE]\n- [NEXT]"}],
    "steps": [
        {"title": "Collect numbers", "what_to_do": "Pull the figures", "how": "From the tracker", "done_when": "You have 5 numbers", "minutes": 30, "watch_out": "Old data"},
        {"title": "Write it up", "what_to_do": "Fill the template", "how": "Short sentences", "done_when": "One page", "minutes": "45", "watch_out": ""},
    ],
    "quality_check": ["Fits one page?"], "common_mistakes": ["Too long"], "total_time": "about 90 minutes",
}


def _user(db):
    _n[0] += 1
    u = models.User(email=f"tg{_n[0]}@x.com", hashed_password="x", full_name="T", resume_text="Analyst")
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _as(u):
    app.dependency_overrides[get_current_user] = lambda: u


def _build(u, built=None):
    _as(u)
    with patch(f"{SVC}.build", return_value=built or task_guide.parse(json.dumps(GOOD))):
        return client.post("/task-guides", json={"task": "Write the weekly status report for my team", "role": "Analyst", "level": "first_time"})


def test_parse_normalises_and_numbers_steps():
    d = task_guide.parse("```json\n" + json.dumps(GOOD) + "\n```")
    assert [s["id"] for s in d["steps"]] == ["s1", "s2"]
    assert d["steps"][1]["minutes"] == 45
    assert d["requirements"][1] == {"item": "Access to the tracker", "why": ""}
    assert d["materials"][0]["template"].startswith("# Status")


def test_parse_rejects_thin_guides():
    with pytest.raises(ValueError):
        task_guide.parse(json.dumps({"goal": "x" * 10, "steps": [{"title": "only one"}]}))
    with pytest.raises(ValueError):
        task_guide.parse("not json")


def test_build_saves_and_counts(db):
    u = _user(db)
    r = _build(u)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Weekly status report" and body["level"] == "first_time"
    assert len(body["steps"]) == 2 and body["done"] == []
    db.expire_all()
    assert usage.get_usage(db, u.id, "task_guide") == 1
    assert client.get("/task-guides").json()[0]["steps"] == 2


def test_failed_build_is_not_counted(db):
    u = _user(db)
    _as(u)
    with patch(f"{SVC}.build", side_effect=RuntimeError("boom")):
        r = client.post("/task-guides", json={"task": "Write the weekly status report for my team"})
    assert r.status_code == 502
    db.expire_all()
    assert usage.get_usage(db, u.id, "task_guide") == 0


def test_progress_keeps_only_real_steps(db):
    u = _user(db)
    gid = _build(u).json()["id"]
    r = client.put(f"/task-guides/{gid}/progress", json={"done": ["s2", "s2", "s9", "x"]})
    assert r.json()["done"] == ["s2"]
    assert client.get("/task-guides").json()[0]["done"] == 1


def test_help_and_metering(db):
    u = _user(db)
    gid = _build(u).json()["id"]
    with patch(f"{SVC}.help_reply", return_value="Looks good; add the dates.") as h:
        r = client.post(f"/task-guides/{gid}/help", json={"step_id": "s1", "message": "Here is my draft: ...", "history": []})
    assert r.json() == {"reply": "Looks good; add the dates."}
    assert h.called
    db.expire_all()
    assert usage.get_usage(db, u.id, "coaching_message") == 1
    with patch(f"{SVC}.help_reply", side_effect=RuntimeError("x")):
        assert client.post(f"/task-guides/{gid}/help", json={"step_id": "s1", "message": "hello there"}).status_code == 502
    db.expire_all()
    assert usage.get_usage(db, u.id, "coaching_message") == 1


def test_other_users_cannot_see_or_change_a_guide(db):
    a, b = _user(db), _user(db)
    gid = _build(a).json()["id"]
    _as(b)
    assert client.get(f"/task-guides/{gid}").status_code == 404
    assert client.put(f"/task-guides/{gid}/progress", json={"done": []}).status_code == 404
    assert client.delete(f"/task-guides/{gid}").status_code == 404
    assert client.get("/task-guides").json() == []


def test_delete(db):
    u = _user(db)
    gid = _build(u).json()["id"]
    assert client.delete(f"/task-guides/{gid}").json() == {"ok": True}
    assert client.get(f"/task-guides/{gid}").status_code == 404


def test_task_text_must_be_real():
    r = client.post("/task-guides", json={"task": "hi"})
    assert r.status_code in (401, 403, 422)


def test_help_reply_builds_a_clean_conversation():
    fake = MagicMock()
    fake.messages.create.return_value = MagicMock(content=[MagicMock(text="ok")])
    guide = task_guide.parse(json.dumps(GOOD))
    with patch.object(task_guide, "client", fake):
        out = task_guide.help_reply("task", guide, "s1", "my draft", [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "q"}], "first_time")
    assert out == "ok"
    kw = fake.messages.create.call_args.kwargs
    assert kw["messages"][0]["role"] == "user" and kw["messages"][-1]["content"] == "my draft"
    assert "Collect numbers" in kw["system"]
