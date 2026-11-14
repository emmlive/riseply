"""The submitter only says "submitted" when the site confirms it, and stops for a
person when a required question or the resume attachment is missing."""
import http.server
import tempfile
import threading

import pytest

from app.config import settings
from app.services import submitter

BASIC = """
<label for=fn>First name</label><input id=fn name=fn required>
<label for=ln>Last name</label><input id=ln name=ln required>
<label for=em>Email</label><input id=em name=em type=email required>
<label for=ph>Phone</label><input id=ph name=ph>
"""
RESUME = "<label for=cv>Resume</label><input id=cv type=file required>"

PAGES = {
    # Confirms like Greenhouse: swaps the form for a thank-you message.
    "/good": f"""<form id=f onsubmit="event.preventDefault();fetch('/hit',{{method:'POST'}});document.body.innerHTML='<h1>Thank you for applying.</h1>'">
        {BASIC}{RESUME}<button type=submit>Submit Application</button></form>""",
    # A required legal question the standard fields cannot answer.
    "/question": f"""<form onsubmit="event.preventDefault();fetch('/hit',{{method:'POST'}})">{BASIC}{RESUME}
        <label for=wa>Are you legally authorized to work here?</label>
        <select id=wa required><option value=''>Select</option><option>Yes</option><option>No</option></select>
        <button type=submit>Submit Application</button></form>""",
    # Clicking Submit shows an error instead of accepting.
    "/rejects": f"""<form onsubmit="event.preventDefault();fetch('/hit',{{method:'POST'}});
        document.getElementById('e').innerText='This field is required';document.getElementById('ph').setAttribute('aria-invalid','true')">
        {BASIC}{RESUME}<div id=e></div><button type=submit>Submit Application</button></form>""",
    # Clicking Submit does nothing the page can show.
    "/silent": f"""<form onsubmit="event.preventDefault();fetch('/hit',{{method:'POST'}})">{BASIC}{RESUME}
        <button type=submit>Submit Application</button></form>""",
    # No place to attach a resume at all.
    "/noresume": f"""<form onsubmit="event.preventDefault();fetch('/hit',{{method:'POST'}})">{BASIC}
        <button type=submit>Submit Application</button></form>""",
}


@pytest.fixture(scope="module")
def site():
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = PAGES.get(self.path.split("?")[0], "").encode()
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>" + body + b"</body></html>")

        def do_POST(self):
            hits.append(self.path)
            self.send_response(204)
            self.end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"127.0.0.1:{srv.server_address[1]}"
    old = settings.auto_submit_allowed_domains
    settings.auto_submit_allowed_domains = host
    yield host, hits
    settings.auto_submit_allowed_domains = old
    srv.shutdown()


CAND = {"first_name": "Em", "last_name": "O", "full_name": "Em O", "email": "e@example.com", "phone": "2405550100",
        "location": "Chicago", "linkedin_url": "", "portfolio_url": ""}


@pytest.fixture()
def resume():
    f = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    f.write(b"PK fake resume")
    f.close()
    return f.name


def _run(site, path, resume, submit=True):
    host, hits = site
    hits.clear()
    r = submitter.submit_application(f"http://{host}{path}", resume, CAND, actually_submit=submit)
    return r, list(hits)


def test_confirmed_submission_is_reported_submitted(site, resume):
    r, hits = _run(site, "/good", resume)
    assert r["status"] == "submitted" and hits == ["/hit"]


def test_a_required_question_it_cannot_answer_stops_before_clicking_submit(site, resume):
    r, hits = _run(site, "/question", resume)
    assert r["status"] == "needs_manual_review" and "legally authorized" in r["detail"].lower()
    assert hits == [], "must not click Submit with an unanswered required question"


def test_a_form_that_rejects_the_submit_is_not_reported_submitted(site, resume):
    r, hits = _run(site, "/rejects", resume)
    assert r["status"] == "needs_manual_review" and "wasn't accepted" in r["detail"] and hits == ["/hit"]


def test_a_submit_the_site_never_confirms_is_not_reported_submitted(site, resume):
    r, _ = _run(site, "/silent", resume)
    assert r["status"] == "needs_manual_review" and "never confirmed" in r["detail"]


def test_a_resume_that_did_not_attach_stops_before_clicking_submit(site, resume):
    r, hits = _run(site, "/noresume", resume)
    assert r["status"] == "needs_manual_review" and "resume didn't attach" in r["detail"] and hits == []


def test_fill_only_mode_never_submits(site, resume):
    r, hits = _run(site, "/good", resume, submit=False)
    assert r["status"] == "needs_manual_review" and hits == []


def test_linkedin_stays_blocked_whatever_the_allowlist_says(monkeypatch):
    monkeypatch.setattr(settings, "auto_submit_allowed_domains", "www.linkedin.com,linkedin.com")
    ok, why = submitter.is_supported_ats("https://www.linkedin.com/jobs/view/1")
    assert not ok and "blocked" in why
