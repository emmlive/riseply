"""Coach videos: found by search (never named by the model), safe ids only,
cached, metered only on a fresh search, and always a link fallback."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import usage, videos

PAYLOAD = {"items": [
    {"id": {"videoId": "dQw4w9WgXcQ"}, "snippet": {"title": "Qualys  basics", "channelTitle": "Sec Channel",
                                                  "thumbnails": {"medium": {"url": "https://i.ytimg.com/x.jpg"}}}},
    {"id": {"videoId": "bad id!"}, "snippet": {"title": "nope"}},
    {"id": {"videoId": "abcdefghijk"}, "snippet": {"title": "Second", "thumbnails": {"default": {"url": "javascript:alert(1)"}}}},
]}


def test_parse_keeps_only_valid_ids_and_https_thumbnails():
    out = videos.parse(PAYLOAD)
    assert [v["id"] for v in out] == ["dQw4w9WgXcQ", "abcdefghijk"]
    assert out[0]["title"] == "Qualys basics" and out[1]["thumb"] == ""


def test_search_phrase_and_link():
    assert videos.search_phrase("Qualys scanning") == "Qualys scanning tutorial"
    assert videos.search_phrase("How to read a SIEM") == "How to read a SIEM"
    assert videos.search_url("a b&c").startswith("https://www.youtube.com/results?search_query=a+b%26c")


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"v-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db
    app.dependency_overrides.clear()
    db.close()


def test_without_an_api_key_it_is_just_the_link(ctx):
    c, _, _ = ctx
    with patch.object(settings, "youtube_api_key", ""), patch.object(videos, "fetch") as f:
        r = c.get("/career-coach/videos", params={"q": "Qualys"})
    assert r.status_code == 200 and r.json()["videos"] == [] and "youtube.com/results" in r.json()["search_url"]
    assert f.call_count == 0


def test_fresh_search_is_metered_then_cached_and_free(ctx):
    c, user, db = ctx
    q = f"topic {uuid.uuid4().hex[:6]}"
    with patch.object(settings, "youtube_api_key", "k"), patch.object(videos, "fetch", return_value=videos.parse(PAYLOAD)) as f:
        before = usage.get_usage(db, user.id, "coach_video")
        r1 = c.get("/career-coach/videos", params={"q": q})
        r2 = c.get("/career-coach/videos", params={"q": q})
    assert len(r1.json()["videos"]) == 2 and r2.json()["videos"] == r1.json()["videos"] and f.call_count == 1
    assert usage.get_usage(db, user.id, "coach_video") == before + 1


def test_failure_is_refunded_and_falls_back_to_the_link(ctx):
    c, user, db = ctx
    before = usage.get_usage(db, user.id, "coach_video")
    with patch.object(settings, "youtube_api_key", "k"), patch.object(videos, "fetch", side_effect=RuntimeError("quota")):
        r = c.get("/career-coach/videos", params={"q": f"fail {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200 and r.json()["videos"] == [] and "Couldn't load" in r.json()["note"]
    assert usage.get_usage(db, user.id, "coach_video") == before


def test_over_the_monthly_allowance_gets_the_link_not_an_error(ctx):
    c, _, _ = ctx
    with patch.object(settings, "youtube_api_key", "k"), patch.dict(usage.FREE_LIMITS, {"coach_video": 0}), \
            patch.object(videos, "fetch") as f:
        r = c.get("/career-coach/videos", params={"q": f"limit {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200 and "used this month" in r.json()["note"] and f.call_count == 0
