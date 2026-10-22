"""Exam prep: outline, question validation, metering, grading, spaced review."""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main
from app.main import app as fastapp
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import exam_prep, admin_stats, usage

client = TestClient(fastapp)
SVC = "app.routers.exams.exam_prep"


def _outline():
    return json.dumps({"name": "CISA", "body": "ISACA", "confidence": "high", "summary": "Audit.", "domains": [
        {"name": "Governance", "weight_pct": 40, "topics": ["a", "b", "c"]},
        {"name": "Controls", "weight_pct": 35, "topics": ["d", "e", "f"]},
        {"name": "Ops", "weight_pct": 25, "topics": ["g", "h", "i"]}]})


def _q(n, correct=1):
    return {"stem": f"Which choice best describes situation number {n} in an audit?", "options": [f"A{n}", f"B{n}", f"C{n}", f"D{n}"],
            "correct": correct, "explanation": "Because B is right.", "topic": "a"}


@pytest.fixture()
def db():
    s = SessionLocal(); yield s; s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    fastapp.dependency_overrides.clear()


def _user(db, pro=False):
    u = models.User(email=f"ex{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T")
    db.add(u); db.commit(); db.refresh(u)
    fastapp.dependency_overrides[get_current_user] = lambda: u
    return u


def _exam(db, u):
    e = models.ExamPrep(user_id=u.id, exam_name="CISA", outline=exam_prep.json.dumps(exam_prep.parse_outline(_outline())))
    db.add(e); db.commit(); db.refresh(e)
    return e


def test_parse_outline_normalises_weights_and_ids():
    o = exam_prep.parse_outline(_outline())
    assert [d["id"] for d in o["domains"]] == ["d1", "d2", "d3"]
    assert sum(d["weight_pct"] for d in o["domains"]) == 100


def test_parse_outline_rejects_too_short():
    with pytest.raises(ValueError):
        exam_prep.parse_outline('{"domains":[{"name":"x","weight_pct":100,"topics":[]}]}')


def test_parse_questions_validates():
    good = _q(1)
    bad = [dict(_q(2), options=["a", "b", "c"]), dict(_q(3), correct=7), dict(_q(4), explanation=""),
           dict(_q(5), options=["x", "x", "y", "z"]), dict(_q(6), stem="short")]
    out = exam_prep.parse_questions(json.dumps({"questions": [good, good] + bad}))
    assert len(out) == 1  # duplicate and invalid dropped
    assert exam_prep.parse_questions(json.dumps({"questions": [good]}), {good["stem"]}) == []


def test_next_due_schedule():
    now = datetime(2026, 1, 1)
    assert exam_prep.next_due(0, True, now) == (1, now + timedelta(days=3))
    assert exam_prep.next_due(3, False, now) == (0, now + timedelta(days=1))
    assert exam_prep.next_due(99, True, now)[0] == len(exam_prep.BOX_DAYS) - 1


def test_weak_domains():
    by = {"d1": {"correct": 9, "total": 10}, "d2": {"correct": 3, "total": 10}, "d3": {"correct": 6, "total": 10}}
    assert exam_prep.weak_domains(by) == ["d2", "d3"]


def test_every_new_action_has_cost():
    for a in ("exam_plan", "exam_questions"):
        assert a in admin_stats.ESTIMATED_COST_PER_ACTION and a in usage.FREE_LIMITS and a in usage.PRO_LIMITS


def test_create_and_failure_refunds(db):
    u = _user(db)
    with patch(f"{SVC}.outline", side_effect=RuntimeError("x")):
        assert client.post("/exams", json={"exam_name": "CISA"}).status_code == 502
    with patch(f"{SVC}.outline", return_value=exam_prep.parse_outline(_outline())):
        r = client.post("/exams", json={"exam_name": "CISA"})
    assert r.status_code == 200 and len(r.json()["domains"]) == 3
    assert "official" in r.json()["note"]


def test_practice_hides_answers_and_grades(db):
    u = _user(db); e = _exam(db, u)
    with patch(f"{SVC}.questions", return_value=[_q(1), _q(2)]):
        r = client.post(f"/exams/{e.id}/practice", json={"domain_id": "d1", "count": 2})
    assert r.status_code == 200
    d = r.json()
    assert all("correct" not in q and "explanation" not in q for q in d["questions"])
    q0 = d["questions"][0]["id"]
    wrong = client.post(f"/exams/attempts/{d['attempt_id']}/answer", json={"question_id": q0, "choice": 0}).json()
    assert wrong["correct"] is False and wrong["correct_index"] == 1 and wrong["explanation"]
    row = db.query(models.ExamQuestion).get(q0); db.refresh(row)
    assert row.times_wrong == 1 and row.box == 0 and row.due_at > datetime.utcnow()
    fin = client.post(f"/exams/attempts/{d['attempt_id']}/finish", json={"answers": []}).json()
    assert fin["total"] == 2 and fin["answered"] == 1


def test_practice_failure_refunds_and_ownership(db):
    u = _user(db); e = _exam(db, u)
    with patch(f"{SVC}.questions", side_effect=RuntimeError("x")):
        assert client.post(f"/exams/{e.id}/practice", json={"domain_id": "d1"}).status_code == 502
    assert client.post(f"/exams/{e.id}/practice", json={"domain_id": "nope"}).status_code == 404
    _user(db)  # another user
    assert client.get(f"/exams/{e.id}").status_code == 404


def test_mock_scores_by_domain_and_weights(db):
    u = _user(db); e = _exam(db, u)
    def fake(exam, domain, count, avoid):
        return [_q(hash((domain["id"], i)) % 100000) for i in range(count)]
    with patch(f"{SVC}.questions", side_effect=fake):
        r = client.post(f"/exams/{e.id}/mock", json={"count": 20, "minutes": 30})
    d = r.json()
    assert r.status_code == 200 and d["time_limit_min"] == 30
    by_dom = {}
    for q in d["questions"]:
        by_dom[q["domain_id"]] = by_dom.get(q["domain_id"], 0) + 1
    assert by_dom["d1"] > by_dom["d3"]
    # answer d1 questions right, everything else wrong
    answers = [{"question_id": q["id"], "choice": 1 if q["domain_id"] == "d1" else 0} for q in d["questions"]]
    fin = client.post(f"/exams/attempts/{d['attempt_id']}/finish", json={"answers": answers}).json()
    dom = {x["id"]: x for x in fin["domains"]}
    assert dom["d1"]["pct"] == 100 and dom["d2"]["pct"] == 0
    assert {s["id"] for s in fin["study_next"]} == {"d2", "d3"}
    assert all("explanation" in x for x in fin["review"])
    # mock cannot be graded per answer
    assert client.post(f"/exams/attempts/{d['attempt_id']}/answer", json={"question_id": d["questions"][0]["id"], "choice": 1}).status_code == 400


def test_review_only_due_and_free(db):
    u = _user(db); e = _exam(db, u)
    assert client.post(f"/exams/{e.id}/review", json={}).status_code == 400
    q = models.ExamQuestion(exam_id=e.id, user_id=u.id, domain_id="d1", stem="s" * 20, options=json.dumps(["a", "b", "c", "d"]),
                            correct=2, explanation="x", times_seen=1, times_wrong=1, due_at=datetime.utcnow() - timedelta(hours=1))
    db.add(q); db.commit()
    r = client.post(f"/exams/{e.id}/review", json={})
    assert r.status_code == 200 and len(r.json()["questions"]) == 1
    ok = client.post(f"/exams/attempts/{r.json()['attempt_id']}/answer", json={"question_id": q.id, "choice": 2}).json()
    assert ok["correct"] is True
    db.refresh(q); assert q.box == 1 and q.due_at > datetime.utcnow() + timedelta(days=2)


def test_delete(db):
    u = _user(db); e = _exam(db, u)
    assert client.delete(f"/exams/{e.id}").status_code == 200
    assert client.get(f"/exams/{e.id}").status_code == 404


def test_schedule_weights_weak_domains_and_final_week():
    from datetime import date
    doms = [{"id": "d1", "name": "A", "weight_pct": 50, "accuracy": 90}, {"id": "d2", "name": "B", "weight_pct": 50, "accuracy": 30},
            {"id": "d3", "name": "C", "weight_pct": 0, "accuracy": None}]
    s = exam_prep.build_schedule(doms, "2026-12-01", 6, today=date(2026, 10, 20))
    assert s["weeks_left"] == 6 and s["final_week"]
    hrs = {t["domain_id"]: t["hours"] for t in s["totals"]}
    assert hrs["d2"] > hrs["d1"]
    assert abs(sum(t["hours"] for t in s["this_week"]) - 6) < 0.3
    assert exam_prep.build_schedule(doms, "2026-10-01", 6, today=date(2026, 10, 20))["past"] is True
    assert exam_prep.build_schedule(doms, "nonsense", 6) is None
    last = exam_prep.build_schedule(doms, "2026-10-25", 6, today=date(2026, 10, 20))
    assert last["weeks_left"] == 1 and last["this_week_is_final"]


def test_schedule_endpoint_and_weak_topics(db):
    u = _user(db); e = _exam(db, u)
    assert client.put(f"/exams/{e.id}/schedule", json={"exam_date": "bad", "hours_per_week": 5}).status_code == 400
    future = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
    r = client.put(f"/exams/{e.id}/schedule", json={"exam_date": future, "hours_per_week": 5}).json()
    assert r["schedule"]["weeks_left"] >= 4 and r["hours_per_week"] == 5
    db.add(models.ExamQuestion(exam_id=e.id, user_id=u.id, domain_id="d1", topic="Risk", stem="s" * 20, options="[]", correct=0, times_seen=2, times_wrong=2))
    db.commit()
    got = client.get(f"/exams/{e.id}").json()
    assert got["domains"][0]["weak_topics"] == ["Risk"]
    assert client.put(f"/exams/{e.id}/schedule", json={"exam_date": "", "hours_per_week": 5}).json()["schedule"] is None
