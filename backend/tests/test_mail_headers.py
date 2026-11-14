"""Alert mail carries a List-Unsubscribe header; receipts and password resets do not."""
import sys
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.services import notifier


def _send(kind, monkeypatch):
    sent = []
    fake = SimpleNamespace(api_key="", Emails=SimpleNamespace(send=lambda params: sent.append(params)))
    monkeypatch.setitem(sys.modules, "resend", fake)
    monkeypatch.setattr(settings, "resend_api_key", "k")
    with patch.object(notifier, "_log_email"):
        notifier.send_email("a@b.com", "s", "body", kind=kind)
    return sent[0]


def test_alert_mail_says_how_to_stop_it(monkeypatch):
    for kind in ("digest", "new_match", "alert_quiet", "test"):
        h = _send(kind, monkeypatch)["headers"]["List-Unsubscribe"]
        assert "/dashboard/profile>" in h and "mailto:" in h


def test_transactional_mail_has_no_unsubscribe_header(monkeypatch):
    for kind in ("password_reset", "welcome", "submitted", "other"):
        assert "headers" not in _send(kind, monkeypatch)
