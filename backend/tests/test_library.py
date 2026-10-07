"""Tests for the Library (/library/*) and the Career Coach's use of it.

The coach may only recommend Library items by id. These tests cover that
protocol end to end (marker -> real card, hallucinated ids dropped,
hidden items disappear, no URLs in the prompt) plus the admin-only
management endpoints. Model calls are monkeypatched like the other
coach tests.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import library as library_service

client = TestClient(app)
_n = [0]
SVC = "app.routers.career_coach.career_coach_service"


def _user(db, admin=False):
    _n[0] += 1
    u = models.User(email=f"lib{_n[0]}@x.com", hashed_password="x", full_name="T",
                    resume_text="Brewer, 2 years.", is_admin=admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _item(db, title="Zymurgy Basics", fields="zymurgy,brewing", active=True, url="https://example.com/z"):
    it = models.LibraryItem(title=title, url=url, description="Intro to fermentation science.",
                            resource_type="course", fields=fields, level="beginner", cost="free", active=active)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _login(u):
    app.dependency_overrides[get_current_user] = lambda: u


# ---- Library endpoints -----------------------------------------------------

def test_starter_library_is_seeded(db):
    assert db.query(models.LibraryItem).count() >= 10


def test_any_user_can_browse_and_search(db):
    u = _user(db)
    _item(db, title="Quixotic Cartography", fields="cartography,maps")
    _login(u)
    assert client.get("/library/items").status_code == 200
    hits = client.get("/library/items", params={"q": "cartography"}).json()
    assert [h["title"] for h in hits] == ["Quixotic Cartography"]
    assert hits[0]["fields"] == ["cartography", "maps"]
    assert client.get("/library/items", params={"q": "carto"}).json()  # substring fallback


def test_only_admins_manage_items(db):
    member, admin = _user(db), _user(db, admin=True)
    body = {"title": "New Resource", "url": "https://example.com/new", "fields": ["SQL ", "sql", "Data"]}
    _login(member)
    assert client.post("/library/items", json=body).status_code == 403

    _login(admin)
    created = client.post("/library/items", json=body)
    assert created.status_code == 200
    item = created.json()
    assert item["fields"] == ["sql", "data"]  # normalized + deduped
    upd = client.put(f"/library/items/{item['id']}", json={**body, "title": "Renamed", "active": False})
    assert upd.json()["title"] == "Renamed" and upd.json()["active"] is False
    assert client.delete(f"/library/items/{item['id']}").status_code == 200
    assert client.delete(f"/library/items/{item['id']}").status_code == 404

    _login(member)
    assert client.put(f"/library/items/{item['id']}", json=body).status_code == 403
    assert client.delete(f"/library/items/{item['id']}").status_code == 403


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "ftp://x.com/a", "example.com"])
def test_rejects_non_http_urls(db, url):
    _login(_user(db, admin=True))
    assert client.post("/library/items", json={"title": "Bad", "url": url}).status_code == 422


def test_hidden_items_only_visible_to_admins_who_ask(db):
    member, admin = _user(db), _user(db, admin=True)
    _item(db, title="Hidden Gem Ostrich", fields="ostrich", active=False)
    _login(member)
    assert client.get("/library/items", params={"q": "ostrich", "include_inactive": True}).json() == []
    _login(admin)
    assert client.get("/library/items", params={"q": "ostrich"}).json() == []
    assert len(client.get("/library/items", params={"q": "ostrich", "include_inactive": True}).json()) == 1


# ---- Coach integration -----------------------------------------------------

def _start(user, role="Zymurgy Brewer"):
    _login(user)
    offered_ids = []

    def fake_start(*args, library=None, **kwargs):
        # Capture ids at call time: the request's DB session closes
        # afterwards, so the ORM objects can't be inspected later.
        offered_ids.extend(i.id for i in (library or []))
        return {"topic": "Fermentation", "opening_message": "Hi."}

    with patch(f"{SVC}.start_session", side_effect=fake_start):
        resp = client.post("/career-coach/sessions", json={"session_type": "drill", "target_role": role})
    return resp, offered_ids


def test_start_offers_relevant_library_items_to_the_model(db):
    u = _user(db)
    it = _item(db)
    resp, offered_ids = _start(u)
    assert resp.status_code == 200
    assert it.id in offered_ids


def test_reply_marker_becomes_resource_and_bad_ids_are_dropped(db):
    u = _user(db)
    it = _item(db)
    sid = _start(u)[0].json()["session"]["id"]
    _login(u)
    raw = f"Study fermentation basics. [[lib:{it.id}]] Also [[lib:99999999]] this."
    offered_ids = []

    def fake_reply(*args, library=None, **kwargs):
        offered_ids.extend(i.id for i in (library or []))
        return raw

    with patch(f"{SVC}.reply", side_effect=fake_reply):
        resp = client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "how do I learn zymurgy?"})
    assert it.id in offered_ids
    body = resp.json()
    assert "[[" not in body["content"]
    assert [r["id"] for r in body["resources"]] == [it.id]
    assert body["resources"][0]["url"] == "https://example.com/z"
    # The invented id was removed before saving, not just hidden on display.
    saved = db.query(models.CareerCoachMessage).filter_by(session_id=sid, role="assistant").order_by(models.CareerCoachMessage.id.desc()).first()
    assert "99999999" not in saved.content and f"[[lib:{it.id}]]" in saved.content


def test_history_resolves_resources_and_hidden_items_vanish(db):
    u = _user(db)
    it = _item(db)
    sid = _start(u)[0].json()["session"]["id"]
    _login(u)
    with patch(f"{SVC}.reply", return_value=f"Read this. [[lib:{it.id}]]"):
        client.post(f"/career-coach/sessions/{sid}/messages", json={"message": "zymurgy?"})
    msgs = client.get(f"/career-coach/sessions/{sid}/messages").json()
    assert [r["id"] for r in msgs[-1]["resources"]] == [it.id]

    it.active = False
    db.commit()
    msgs = client.get(f"/career-coach/sessions/{sid}/messages").json()
    assert msgs[-1]["resources"] == [] and "[[" not in msgs[-1]["content"]


def test_session_library_shelf_is_scoped_and_relevant(db):
    owner, other = _user(db), _user(db)
    it = _item(db)
    sid = _start(owner)[0].json()["session"]["id"]
    _login(owner)
    assert it.id in [i["id"] for i in client.get(f"/career-coach/sessions/{sid}/library").json()]
    _login(other)
    assert client.get(f"/career-coach/sessions/{sid}/library").status_code == 404


# ---- Service-level ---------------------------------------------------------

def test_prompt_block_lists_ids_but_never_urls(db):
    it = _item(db, url="https://secret.example.com/path")
    block = library_service.prompt_block([it])
    assert f"[ID {it.id}]" in block and "secret.example.com" not in block
    assert "do not recommend any" in library_service.prompt_block([])


def test_retrieve_ignores_inactive_and_unrelated(db):
    a = _item(db, title="Alpacas Handbook", fields="alpaca", active=True)
    b = _item(db, title="Alpacas Hidden", fields="alpaca", active=False)
    got = library_service.retrieve([a, b], "alpaca farming")
    assert got == [a]
    assert library_service.retrieve([a], "quantum chromodynamics") == []
