"""Generate the ATS resume from the extension, attach it, and mark the job applied."""
import base64
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.routers.extension import _job_keys

POSTING = ("Security Compliance Specialist at Crypto Co. You will lead SOX and IT general controls "
           "audits, test access controls, and report to the Audit Director. CISA preferred. " * 2)
URL = "https://jobs.lever.co/crypto/47509c3a-b034-470b-903a-b8e0441d5d28"
BLOCKS = [{"type": "name", "text": "Jane"}]


@pytest.fixture()
def setup():
    db = SessionLocal()
    user = models.User(email=f"xt-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
                       resume_text="Senior IT Auditor with CISA, 9 years of SOX work.")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def _fakes():
    return (
        patch("app.routers.pipeline.matcher.score_job", return_value={"score": 81, "reason": "Good fit."}),
        patch("app.routers.pipeline.resume_customizer.customize_for_job",
              return_value=("jane_crypto.docx", b"docx", "Led with SOX work.")),
        patch("app.services.resume_customizer.docx_to_blocks", return_value=BLOCKS),
        patch("app.services.resume_customizer.ats_checks", return_value={"pages": 1.4, "checks": [{"label": "Plain layout", "ok": True, "detail": "x"}]}),
        patch("app.services.resume_customizer.build_pdf_from_blocks", return_value=b"%PDF-1.4 tailored"),
    )


def _body(**k):
    return {"description": POSTING, "title": "Security Compliance Specialist", "company": "Crypto Co",
            "url": URL + "/apply#section", **k}


def test_job_keys_treat_apply_page_as_the_posting():
    assert _job_keys(URL + "/apply")[0] == _job_keys(URL)[0]
    assert _job_keys("https://www.indeed.com/viewjob?jk=1")[1] == "", "one-segment paths never match loosely"
    assert _job_keys("javascript:alert(1)") == ("", "")


def test_generate_attach_and_mark_applied(setup):
    db, user, client = setup
    a, b, c, d, e = _fakes()
    with a, b, c, d, e:
        assert client.post("/extension/job-status", json={"url": URL + "/apply"}).json() == {"in_list": False}
        r = client.post("/extension/tailor", json=_body())
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["created"] and t["has_tailored"] and t["match_score"] == 81 and t["applied"] is False
        assert t["rationale"] == "Led with SOX work." and t["ats"][0]["label"] == "Plain layout"

        # the apply page of the same posting is recognised, and a second press costs nothing
        s = client.post("/extension/job-status", json={"url": URL + "/apply"}).json()
        assert s["in_list"] and s["application_id"] == t["application_id"] and s["has_tailored"]
        again = client.post("/extension/tailor", json=_body())
        assert again.json()["created"] is False and again.json()["application_id"] == t["application_id"]

        f = client.get("/extension/resume-file", params={"application_id": t["application_id"]}).json()
        assert f["source"] == "tailored" and f["filename"] == "jane_crypto.pdf"
        assert base64.b64decode(f["data"]).startswith(b"%PDF")

        m = client.post("/extension/applied", json={"application_id": t["application_id"]}).json()
        assert m == {"found": True, "already": False, "status": "submitted"}
        m2 = client.post("/extension/applied", json={"url": URL}).json()
        assert m2["already"] is True, "never counted twice"
    row = db.query(models.Application).filter_by(id=t["application_id"]).first()
    assert row.status == "submitted" and row.submitted_at is not None


def test_applied_does_nothing_for_a_job_not_in_the_list(setup):
    db, user, client = setup
    assert client.post("/extension/applied", json={"url": "https://x.com/jobs/a/b"}).json() == {"found": False}
    assert client.post("/extension/applied", json={"application_id": 999999999}).json() == {"found": False}


def test_other_peoples_applications_are_invisible(setup):
    db, user, client = setup
    a, b, c, d, e = _fakes()
    with a, b, c, d, e:
        t = client.post("/extension/tailor", json=_body()).json()
    other = models.User(email=f"xt-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="x")
    db.add(other); db.commit(); db.refresh(other)
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.post("/extension/job-status", json={"url": URL}).json() == {"in_list": False}
    assert client.post("/extension/applied", json={"application_id": t["application_id"]}).json() == {"found": False}
    f = client.get("/extension/resume-file", params={"application_id": t["application_id"]})
    assert f.json()["source"] == "generated", "no tailored file leaks; falls back to the person's own resume"


def test_existing_job_without_a_tailored_resume_is_retailored(setup):
    db, user, client = setup
    job = models.Job(source="greenhouse", external_id=f"g-{uuid.uuid4().hex[:6]}", company="Crypto Co",
                     title="Specialist", location="", url=URL, description=POSTING, is_active=True)
    db.add(job); db.commit(); db.refresh(job)
    ap = models.Application(user_id=user.id, job_id=job.id, matched_profile="p", match_score=70, match_reason="ok")
    db.add(ap); db.commit(); db.refresh(ap)
    a, b, c, d, e = _fakes()
    with a, b, c, d, e:
        t = client.post("/extension/tailor", json=_body()).json()
    assert t["application_id"] == ap.id and t["created"] is False and t["has_tailored"]
