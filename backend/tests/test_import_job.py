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


def test_already_applied_saves_as_submitted_without_tailoring(setup):
    db, user, client = setup
    a, b, _ = _fakes()
    with a, b, patch("app.routers.pipeline.resume_customizer.customize_for_job") as tailor:
        r = client.post("/applications/import", json={"description": POSTING, "already_applied": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "submitted" and body["submitted_at"] and body["status_updated_at"]
    tailor.assert_not_called()


def test_mark_submitted_works_straight_from_awaiting_review(setup):
    db, user, client = setup
    a, b, c = _fakes()
    with a, b, c:
        app_id = client.post("/applications/import", json={"description": POSTING}).json()["id"]
    assert client.post(f"/applications/{app_id}/mark-submitted").json() == {"status": "submitted"}
    assert client.get(f"/applications/{app_id}").json()["status"] == "submitted"


# ---- jobs far from the resume or the profile ----
from app.services import resume_customizer

FAR_POSTING = ("Registered Nurse, ICU, Dallas, TX. Provide patient care, administer medication, chart in Epic, "
               "ACLS and BLS certification required. Patient safety, patient care, bedside monitoring. " * 3)


def test_added_job_far_from_resume_and_profile_is_still_scored_and_tailored(setup):
    """The person chose this job: neither the location filter nor the field
    check may drop it, even with a search profile set to another city."""
    import json
    db, user, client = setup
    db.add(models.SearchProfile(user_id=user.id, name="Audit", titles=json.dumps(["IT Auditor"]),
                                locations=json.dumps(["Chicago, IL"]), seniority="[]", min_match_score=60,
                                exclude_companies="[]", keywords_required="[]", keywords_excluded="[]", active=True))
    db.commit()
    calls = {}

    def fake_score(resume, job, profile):
        calls["ignore_location"] = profile.get("ignore_location")
        return {"score": 22, "reason": "Different field."}

    with patch("app.routers.pipeline.matcher.score_job", side_effect=fake_score), \
         patch("app.routers.pipeline.resume_customizer.customize_for_job",
               return_value=("resume.docx", b"docx", "Career-change resume. Leads with controls testing.")) as tailor:
        r = client.post("/applications/import", json={"description": FAR_POSTING, "title": "ICU Nurse", "company": "Hosp", "location": "Dallas, TX"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["match_score"] == 22 and body["matched_profile"] == "Audit"
    assert body["tailoring_rationale"].startswith("Career-change resume.")
    assert calls["ignore_location"] is True
    assert tailor.called


def test_prompt_tells_the_model_how_close_the_job_is_and_how_to_pivot():
    resume = "Senior IT Auditor with CISA, 9 years of SOX work, access reviews, ITGC testing, risk assessments."
    far = resume_customizer._build_prompt(resume, {"title": "ICU Nurse", "company": "H", "description": FAR_POSTING, "match_score": 22})
    assert "DECIDE THE APPROACH FIRST" in far and "career_change" in far
    assert "Match score from the scorer: 22" in far
    assert "Transferable Skills" in far and "Never claim the target job title" in far
    assert "Share of the posting's key terms found on the resume:" in far


def test_career_change_and_stretch_get_labelled_even_if_the_model_forgets():
    import json as _json
    resume_json = {"name": "A B", "headline": "x", "contact": [], "sections": [{"heading": "Professional Summary", "kind": "text", "text": "Auditor moving into operations."}]}
    for approach, label in (("career_change", "Career-change resume."), ("transferable", "Stretch role."), ("standard", None)):
        reply = _json.dumps({"approach": approach, "rationale": "Moved controls testing up.", "resume": resume_json})
        fake = type("R", (), {"content": [type("C", (), {"text": reply})()]})()
        with patch.object(resume_customizer.client.messages, "create", return_value=fake):
            rationale, blocks = resume_customizer.tailor_resume("resume text", {"title": "t", "company": "c", "description": "d"})
        assert blocks
        assert rationale.startswith(label) if label else rationale == "Moved controls testing up."


def test_retailor_passes_the_stored_match_score(setup):
    db, user, client = setup
    a, b, c = _fakes()
    with a, b, c:
        app_id = client.post("/applications/import", json={"description": POSTING}).json()["id"]
    seen = {}

    def spy(user_id, resume, job, application_id, facts=None):
        seen.update(job)
        return "r.docx", b"d", "ok"

    with patch("app.routers.pipeline.resume_customizer.customize_for_job", side_effect=spy):
        r = client.post(f"/applications/{app_id}/retailor")
    assert r.status_code == 200, r.text
    assert seen["match_score"] == 88
