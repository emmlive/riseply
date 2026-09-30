"""Unit tests for app.services.coaching's response-parsing helpers.

start_coaching_session, coaching_reply, and finish_coaching_session all
call the real Anthropic client, so those are covered end-to-end (with
the client mocked) via the router tests in test_coaching.py. This file
isolates just the parsing logic (_split_marker_response and the score
extraction in finish_coaching_session) against realistic and malformed
model output, since that's the part most likely to break quietly if a
future prompt tweak changes the model's output shape.
"""
from unittest.mock import MagicMock, patch

from app.services import coaching


def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_split_marker_response_well_formed():
    value, rest = coaching._split_marker_response(
        "TOPIC: Handling a late shipment\n---\nHey, this is the third time this order's been late.",
        "TOPIC:",
    )
    assert value == "Handling a late shipment"
    assert rest == "Hey, this is the third time this order's been late."


def test_split_marker_response_missing_marker_falls_back_to_whole_text():
    value, rest = coaching._split_marker_response("Just an opening line, no marker at all.", "TOPIC:")
    assert value == ""
    assert rest == "Just an opening line, no marker at all."


def test_split_marker_response_missing_separator_still_returns_something():
    # Marker present but no "---" line -- shouldn't crash, and shouldn't
    # silently drop the content either.
    value, rest = coaching._split_marker_response("TOPIC: Foo\nNo separator here.", "TOPIC:")
    assert value == "Foo"
    assert rest  # non-empty, degrades gracefully rather than losing the message


def test_start_coaching_session_uses_given_topic_when_model_omits_marker(monkeypatch):
    monkeypatch.setattr(coaching, "client", MagicMock())
    coaching.client.messages.create.return_value = _fake_response("Just jumping straight into the scenario, no TOPIC line.")

    result = coaching.start_coaching_session(
        "roleplay", "Difficult coworker", "resume", {"title": "Nurse", "company": "Acme", "description": "d"},
    )
    assert result["topic"] == "Difficult coworker"  # falls back to the caller-supplied topic
    assert "TOPIC line" in result["opening_message"]


def test_finish_coaching_session_parses_score_and_feedback(monkeypatch):
    monkeypatch.setattr(coaching, "client", MagicMock())
    coaching.client.messages.create.return_value = _fake_response(
        "SCORE: 78\n---\nGood on empathy, missed confirming the order number."
    )

    result = coaching.finish_coaching_session(
        "roleplay", "Angry customer", "resume", {"title": "Support", "company": "Acme", "description": "d"},
        [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "sorry about that"}],
    )
    assert result["score"] == 78
    assert result["feedback"] == "Good on empathy, missed confirming the order number."


def test_finish_coaching_session_clamps_out_of_range_score(monkeypatch):
    monkeypatch.setattr(coaching, "client", MagicMock())
    coaching.client.messages.create.return_value = _fake_response("SCORE: 140\n---\nWay overstated by the model.")

    result = coaching.finish_coaching_session(
        "drill", "Triage", "resume", {"title": "Nurse", "company": "Acme", "description": "d"},
        [{"role": "assistant", "content": "q"}, {"role": "user", "content": "a"}],
    )
    assert result["score"] == 100


def test_finish_coaching_session_returns_none_score_when_unparseable(monkeypatch):
    monkeypatch.setattr(coaching, "client", MagicMock())
    coaching.client.messages.create.return_value = _fake_response("The model just wrote prose with no SCORE line at all.")

    result = coaching.finish_coaching_session(
        "walkthrough", "Onboarding a client", "resume", {"title": "PM", "company": "Acme", "description": "d"},
        [{"role": "assistant", "content": "q"}, {"role": "user", "content": "a"}],
    )
    assert result["score"] is None
    assert result["feedback"]  # still returns the model's text as feedback, not silently dropped
