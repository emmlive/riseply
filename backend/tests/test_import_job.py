"""Pasting a job posting from another site: scored, tailored, private to the person."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import pipeline_runner

POSTING = ("Senior IT Auditor at Acme Corp in Chicago, IL. You will lead SOX and IT general controls "
           "audits, test access controls, and report to the Audit Director. CISA preferred. " * 2)


@pytest.fixture()
def setup():
    db = SessionLocal()
    user = models.User(email=f"imp-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
                       resume_text="Senior IT Auditor with CISA, 9 years of SOX work.")
    db.add(user)
    db.commit()
    db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def _fakes():
    return (
        patch("app.routers.pipeline.matcher.extract_job_basics",
              return_value={"title": "Senior IT Auditor", "company": "Acme Corp", "location": "Chicago, IL"}),
        patch("app.routers.pipeline.matcher.score_job", return_value={"score": 88, "reason": "Strong fit."}),
        patch("app.routers.pipeline.resume_customizer.customize_for_job",
              return_value=("resume.docx", b"docx", "Moved audit work up.")),
    )


def test_pasted_job_is_scored_tailored_and_listed(setup):
    db, user, client = setup
    a, b, c = _fakes()
    with a, b, c:
        r = client.post("/applications/import", json={"description": POSTING, "url": "https://indeed.com/viewjob?jk=1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_title"] == "Senior IT Auditor" and body["job_company"] == "Acme Corp"
    assert body["match_score"] == 88 and body["status"] == "pending_approval"
    assert body["has_tailored_resume_data"] is True and body["job_open"] is True
    assert body["job_url"] == "https://indeed.com/viewjob?jk=1"


def test_typed_title_and_company_skip_the_text_reading(setup):
    db, user, client = setup
    a, b, c = _fakes()
    with a as extract, b, c:
        r = client.post("/applications/import", json={"description": POSTING, "title": "Auditor II", "company": "Zed"})
    assert r.json()["job_title"] == "Auditor II"
    extract.assert_not_called()


def test_needs_a_resume_and_a_real_link(setup):
    db, user, client = setup
    a, b, c = _fakes()
    with a, b, c:
        assert client.post("/applications/import", json={"description": POSTING, "url": "javascript:alert(1)"}).status_code == 422
        assert client.post("/applications/import", json={"description": "too short"}).status_code == 422
        user.resume_text = ""
        db.commit()
        assert client.post("/applications/import", json={"description": POSTING}).status_code == 400


def test_failed_tailoring_still_saves_the_job(setup):
    db, user, client = setup
    a, b, _ = _fakes()
    with a, b, patch("app.routers.pipeline.resume_customizer.customize_for_job", side_effect=RuntimeError("boom")):
        r = client.post("/applications/import", json={"description": POSTING})
    assert r.status_code == 200
    assert "Re-tailor" in r.json()["notes"]


def test_pasted_jobs_are_never_matched_to_other_people(setup):
    db, user, client = setup
    a, b, c = _fakes()
    with a, b, c:
        client.post("/applications/import", json={"description": POSTING})
    job = db.query(models.Job).filter_by(source="imported").order_by(models.Job.id.desc()).first()
    visible = db.query(models.Job.id).filter(*pipeline_runner._open_job_filters()).all()
    assert job.id not in {row[0] for row in visible}


def test_same_link_cannot_be_added_twice(setup):
    db, user, client = setup
    a, b, c = _fakes()
    url = f"https://indeed.com/viewjob?jk={uuid.uuid4().hex[:8]}"
    with a, b, c:
        assert client.post("/applications/import", json={"description": POSTING, "url": url}).status_code == 200
        again = client.post("/applications/import", json={"description": POSTING, "url": url})
    assert again.status_code == 409 and "already" in again.json()["detail"]
