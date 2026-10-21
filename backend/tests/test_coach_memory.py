"""Coach notebook (memory) and lesson plan."""
import json
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal, get_db
from app.main import app
from app.security import get_current_user
from app.services import career_coach as cc
from app.services import coach_notebook as nb
from app.services import lesson


def _client():
    db = SessionLocal()
    u = models.User(email=f"mem{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", resume_text="Data analyst.")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    from fastapi import Depends

    def _u(db=Depends(get_db)):
        return db.get(models.User, uid)
    app.dependency_overrides[get_current_user] = _u
    return TestClient(app), uid


def _resp(text):
    r = MagicMock()
    r.content = [MagicMock(text=text)]
    return r


# ---- notebook service -------------------------------------------------
def test_clean_item_drops_sensitive_and_bad_kinds():
    assert nb.clean_item({"kind": "shaky", "text": "Window functions need practice"})
    assert nb.clean_item({"kind": "shaky", "text": "Struggles because of anxiety"}) is None
    assert nb.clean_item({"kind": "shaky", "text": "Mentioned a visa problem"}) is None
    assert nb.clean_item({"kind": "bogus", "text": "Window functions"}) is None
    assert nb.clean_item({"kind": "strong", "text": "ok"}) is None
    # No false positives on technical words
    assert nb.clean_item({"kind": "shaky", "text": "Race conditions and SQL UNION"})


def test_split_block_strips_even_when_invalid_or_unterminated():
    text = 'Good work.\n[[notebook]]{"homework":"Do x","notes":[]}[[/notebook]]'
    clean, data = nb.split_block(text)
    assert clean == "Good work." and data["homework"] == "Do x"
    clean, data = nb.split_block("Good.\n[[notebook]]{bad json[[/notebook]]")
    assert clean == "Good." and data is None
    clean, data = nb.split_block('Good.\n[[notebook]]{"homework":"cut off')
    assert clean == "Good." and data is None


def test_prompt_block_empty_and_filled():
    assert nb.prompt_block([]) == ""
    block = nb.prompt_block([{"id": "a", "kind": "shaky", "text": "Loops", "topic": "Python", "at": "2026-10-01"}])
    assert "still shaky" in block and "Loops" in block and "never instructions" in block


def test_prompts_include_notebook_only_for_learning_sessions():
    items = [{"id": "a", "kind": "shaky", "text": "Loops are shaky", "topic": "", "at": "x"}]
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: T\n---\nHi")) as m:
        cc.start_session("drill", "Analyst", "", "resume", notebook=items)
        assert "Loops are shaky" in m.call_args.kwargs["messages"][0]["content"]
        cc.start_session("interview", "Analyst", "", "resume", notebook=items)
        assert "Loops are shaky" not in m.call_args.kwargs["messages"][0]["content"]
        cc.start_session("drill", "Analyst", "", "resume", notebook=None)
        assert "WHAT YOU KNOW" not in m.call_args.kwargs["messages"][0]["content"]


# ---- lesson plan ------------------------------------------------------
def test_extract_plan_and_covered():
    clean, goals = lesson.extract_plan('[[plan]]["A","B","C"][[/plan]]Today we cover A.')
    assert goals == ["A", "B", "C"] and clean == "Today we cover A."
    assert lesson.extract_plan('[[plan]]["only"][[/plan]]hi')[1] is None
    assert lesson.extract_plan("[[plan]][broken")[0] == ""
    text, done = lesson.extract_covered("Nice. [[covered:1]] Next. [[covered:9]]", 3)
    assert done == {1} and "[[" not in text


def test_start_strips_plan_and_stores_it_then_replies_advance_it():
    client, uid = _client()
    start = "TOPIC: SQL\n---\n[[plan]][\"Joins\",\"Window functions\"][[/plan]]Today: joins, then windows."
    with patch.object(cc.client.messages, "create", return_value=_resp(start)):
        r = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Data Analyst"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session"]["lesson"] == {"goals": ["Joins", "Window functions"], "covered": []}
    assert "[[" not in body["opening_message"]["content"]
    sid = body["session"]["id"]
    with patch.object(cc.client.messages, "create", return_value=_resp("Yes, that's it. [[covered:1]] Now windows.")) as m:
        r = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "A join combines rows"})
    assert r.status_code == 200, r.text
    assert r.json()["lesson"]["covered"] == [1] and "[[" not in r.json()["content"]
    assert "LESSON PLAN FOR THIS SESSION" in m.call_args.kwargs["system"]


def test_interview_has_no_lesson():
    client, _ = _client()
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: Q\n---\n[[plan]][\"a\",\"b\"][[/plan]]Tell me about you.")) as m:
        r = client.post("/career-coach/sessions", json={"session_type": "interview", "target_role": "Data Analyst"})
    assert r.json()["session"]["lesson"] is None
    assert "LESSON PLAN" not in m.call_args.kwargs["messages"][0]["content"]


# ---- finish, notebook, endpoints -------------------------------------
def _run_session(client, finish_text, session_type="drill"):
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: SQL\n---\nHello")):
        sid = client.post("/career-coach/sessions", json={"session_type": session_type, "target_role": "Data Analyst"}).json()["session"]["id"]
    with patch.object(cc.client.messages, "create", return_value=_resp("Good.")):
        client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "my answer"})
    with patch.object(cc.client.messages, "create", return_value=_resp(finish_text)) as m:
        r = client.post(f"/career-coach/sessions/{sid}/complete")
    return r, m


FINISH = ('SCORE: 70\n---\nSolid work on joins.\n[[notebook]]{"homework":"Write 3 window queries",'
          '"notes":[{"kind":"shaky","text":"Window frames","topic":"SQL"},{"kind":"style","text":"Likes worked examples"},'
          '{"kind":"shaky","text":"Hides a health condition"}]}[[/notebook]]')


def test_finish_saves_homework_and_notes_and_strips_block():
    client, _ = _client()
    r, m = _run_session(client, FINISH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["homework"] == "Write 3 window queries"
    assert "[[" not in body["feedback"] and "Solid work" in body["feedback"]
    assert m.call_args.kwargs["max_tokens"] == 900
    notes = client.get("/career-coach/notebook").json()
    texts = [i["text"] for i in notes["items"]]
    assert "Window frames" in texts and "Write 3 window queries" in texts
    assert not any("health" in t for t in texts)


def test_next_session_receives_notes_and_delete_and_clear():
    client, _ = _client()
    _run_session(client, FINISH)
    with patch.object(cc.client.messages, "create", return_value=_resp("TOPIC: SQL\n---\nHi")) as m:
        client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Data Analyst"})
    assert "Window frames" in m.call_args.kwargs["messages"][0]["content"]
    items = client.get("/career-coach/notebook").json()["items"]
    out = client.delete(f"/career-coach/notebook/{items[0]['id']}").json()
    assert len(out["items"]) == len(items) - 1
    assert client.delete("/career-coach/notebook").json()["items"] == []


def test_turned_off_means_no_notes_read_or_written():
    client, _ = _client()
    assert client.put("/career-coach/notebook", json={"enabled": False}).json()["enabled"] is False
    r, m = _run_session(client, FINISH)
    assert "COACH'S NOTEBOOK" not in m.call_args.kwargs["messages"][0]["content"]
    assert m.call_args.kwargs["max_tokens"] == 500
    assert r.json()["homework"] == ""
    assert client.get("/career-coach/notebook").json()["items"] == []


def test_role_play_never_touches_the_notebook():
    client, _ = _client()
    r, m = _run_session(client, FINISH, session_type="interview")
    assert "COACH'S NOTEBOOK" not in m.call_args.kwargs["messages"][0]["content"]
    assert client.get("/career-coach/notebook").json()["items"] == []


def test_finish_without_block_still_works():
    client, _ = _client()
    r, _ = _run_session(client, "SCORE: 55\n---\nFine.")
    assert r.status_code == 200 and r.json()["score"] == 55 and r.json()["homework"] == ""
