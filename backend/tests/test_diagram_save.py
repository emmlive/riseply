import uuid
from unittest.mock import patch

from app import models
from tests.test_career_coach import client, _login_as, SVC, db, _clear_overrides  # noqa: F401


def _session(db):
    u = models.User(email=f"dg{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T", resume_text="Support specialist")
    db.add(u); db.commit(); db.refresh(u)
    _login_as(u)
    with patch(f"{SVC}.start_session", return_value={"topic": "T", "opening_message": "Hi"}):
        return client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": "Data Analyst"}).json()["session"]["id"]


ITEMS = [{"id": "z1", "kind": "zone", "x": 10, "y": 10, "w": 300, "h": 300, "label": "Internet"},
         {"id": "b2", "kind": "box", "x": 50, "y": 100, "w": 128, "h": 46, "label": "Web app"}]


def test_diagram_round_trips_and_starts_empty(db):
    sid = _session(db)
    assert client.get(f"/career-coach/sessions/{sid}/diagram").json() == {"items": [], "links": [], "note": ""}
    body = {"items": ITEMS, "links": [{"id": "l3", "from": "b2", "to": "z1", "label": "x"}], "note": "why"}
    assert client.put(f"/career-coach/sessions/{sid}/diagram", json=body).status_code == 200
    got = client.get(f"/career-coach/sessions/{sid}/diagram").json()
    assert got["items"][1]["label"] == "Web app" and got["links"][0]["from"] == "b2" and got["note"] == "why"


def test_arrows_to_missing_shapes_are_dropped_and_bad_data_rejected(db):
    sid = _session(db)
    url = f"/career-coach/sessions/{sid}/diagram"
    r = client.put(url, json={"items": ITEMS, "links": [{"id": "l1", "from": "b2", "to": "gone"}]})
    assert r.json()["links"] == []
    assert client.put(url, json={"items": [{**ITEMS[0], "kind": "circle"}]}).status_code == 422
    assert client.put(url, json={"items": [ITEMS[0]] * 41}).status_code == 422


def test_diagram_is_private(db):
    sid = _session(db)
    _session(db)
    assert client.get(f"/career-coach/sessions/{sid}/diagram").status_code == 404
