"""Pictures attached to a coach message: validation, hand-off to the model, and what is saved."""
import base64
from unittest.mock import patch, MagicMock

import uuid

from app import models
from tests.test_career_coach import client, _login_as, _start, SVC, db, _clear_overrides  # noqa: F401
from app.services import career_coach as cc

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


def _session(db):
    u = models.User(email=f"img{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="T", resume_text="Support specialist")
    db.add(u); db.commit(); db.refresh(u)
    sid = _start(u).json()["session"]["id"]
    return u, sid


def test_images_reach_the_model_and_saved_text_notes_them(db):
    u, sid = _session(db)
    with patch(f"{SVC}.reply", return_value="I see two boxes.") as r:
        res = client.post(f"/career-coach/sessions/{sid}/messages", json={
            "message": "My diagram", "images": [{"media_type": "image/png", "data": PNG}]})
    assert res.status_code == 200
    assert r.call_args.kwargs["images"] == [{"media_type": "image/png", "data": PNG}]
    saved = client.get(f"/career-coach/sessions/{sid}/messages").json()
    assert saved[-2]["content"].endswith("[Attached 1 picture]") and PNG not in saved[-2]["content"]


def test_bad_images_are_rejected(db):
    u, sid = _session(db)
    url = f"/career-coach/sessions/{sid}/messages"
    ok = {"media_type": "image/png", "data": PNG}
    assert client.post(url, json={"message": "x", "images": [{"media_type": "image/svg+xml", "data": PNG}]}).status_code == 422
    assert client.post(url, json={"message": "x", "images": [{"media_type": "image/png", "data": "not base64!!!!!!!!!!!!!!!"}]}).status_code == 422
    assert client.post(url, json={"message": "x", "images": [ok, ok, ok]}).status_code == 422


def test_service_sends_image_blocks_for_this_turn_only():
    fake = MagicMock()
    fake.messages.create.return_value.content = [MagicMock(text="ok")]
    with patch.object(cc, "client", fake):
        cc.reply("upskill", "Role X", "t", "resume", [{"role": "assistant", "content": "hi"}], "my work",
                 images=[{"media_type": "image/png", "data": PNG}])
    last = fake.messages.create.call_args.kwargs["messages"][-1]["content"]
    assert last[0]["type"] == "image" and last[1]["type"] == "text" and "my work" in last[1]["text"]
