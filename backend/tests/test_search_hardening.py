"""Job search hardening: search by profile + default resume, and never
offer a job that has closed."""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, get_db
from app import models
from app.security import get_current_user
from app.services import pipeline_runner, posting_check, search_terms, matcher

RESUME = """JANE DOE
Experience
Senior IT Auditor, Acme Corp  2019 - Present
- Managed audits for SOX
Compliance Analyst at Beta LLC (2015-2019)
Skills: python
"""


@pytest.fixture()
def db():
    s = SessionLocal()
    s.query(models.NearMissResult).delete()
    s.query(models.Application).delete()
    s.query(models.ScoredJob).delete()
    s.query(models.Job).delete()
    s.query(models.SearchProfile).delete()
    s.commit()
    yield s
    s.close()
    app.dependency_overrides.clear()


def _user(db, resume=RESUME, **kw):
    u = models.User(email=f"sh{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", resume_text=resume, **kw)
    db.add(u)
    db.commit()
    return u


def _profile(db, uid, titles, excluded=None):
    db.add(models.SearchProfile(
        user_id=uid, name="P", titles=json.dumps(titles), locations=json.dumps([]), seniority=json.dumps([]),
        min_match_score=60, exclude_companies=json.dumps([]), keywords_required=json.dumps([]),
        keywords_excluded=json.dumps(excluded or []), active=True))
    db.commit()


def _job(db, title, **kw):
    fields = dict(source="t", external_id=uuid.uuid4().hex, company="Acme", title=title, location="Remote",
                  description="d", url="https://acme.example/" + uuid.uuid4().hex, discovered_at=datetime.utcnow())
    fields.update(kw)
    j = models.Job(**fields)
    db.add(j)
    db.commit()
    return j


def _good(job, resume, profiles, ignore_location=False):
    return {"profile_name": profiles[0]["name"], "score": 90, "reason": "r", "meets_threshold": True}


def _run(db, user, **kw):
    scored = []
    def fake(job, resume, profiles, ignore_location=False):
        scored.append(job["title"])
        return _good(job, resume, profiles)
    with patch.object(matcher, "best_profile_match", side_effect=fake), \
         patch("app.services.pipeline_runner.posting_check.check_posting", return_value=True), \
         patch("app.services.pipeline_runner.resume_customizer.customize_for_job", return_value=("r.docx", b"x", "why")), \
         patch("app.services.pipeline_runner.notifier.notify_new_match"):
        result = pipeline_runner.run_matching_for_user(db, user, skip_usage_metering=True, **kw)
    return scored, result


# --- search by profile + resume ----------------------------------------

def test_resume_titles_are_read_and_cleaned():
    assert search_terms.resume_job_titles(RESUME) == ["Senior IT Auditor", "Compliance Analyst"]
    assert search_terms.resume_job_titles("") == []
    assert search_terms.resume_job_titles("I like walking dogs and baking bread") == []


def test_title_check_needs_a_distinctive_word_not_just_manager():
    p = [{"titles": ["IT Audit Manager"], "keywords_required": [], "keywords_excluded": [], "active": True}]
    assert search_terms.title_fits("Senior IT Auditor", p)
    assert search_terms.title_fits("Internal Audit Lead", p)
    assert not search_terms.title_fits("Sales Manager", p)
    assert not search_terms.title_fits("Registered Nurse", p)
    # nothing distinctive to compare against: never starve the search
    assert search_terms.title_fits("Registered Nurse", [{"titles": ["Manager"], "active": True}])


def test_excluded_keywords_are_enforced_on_the_title():
    p = [{"titles": ["Audit"], "keywords_excluded": ["intern"], "active": True}]
    assert search_terms.title_fits("Audit Associate", p)
    assert not search_terms.title_fits("Audit Intern", p)
    assert search_terms.title_fits("Internal Audit Analyst", p)   # whole words only


def test_off_target_jobs_are_not_scored_and_not_remembered(db):
    u = _user(db)
    _profile(db, u.id, ["IT Auditor"], excluded=["intern"])
    keep = _job(db, "Senior IT Auditor")
    _job(db, "Sales Manager")
    _job(db, "IT Audit Intern")
    scored, result = _run(db, u)
    assert scored == ["Senior IT Auditor"]
    assert result["off_target"] == 2
    # not marked as scored, so editing the profile can bring them back
    assert db.query(models.ScoredJob).filter_by(user_id=u.id).count() == 1
    assert db.query(models.ScoredJob).filter_by(user_id=u.id, job_id=keep.id).count() == 1


def test_resume_only_user_is_searched_by_resume_titles(db):
    u = _user(db, location="Plainfield, IL")
    _job(db, "Compliance Analyst II")
    _job(db, "Pastry Chef")
    scored, result = _run(db, u)
    assert scored == ["Compliance Analyst II"]
    app_row = db.query(models.Application).filter_by(user_id=u.id).one()
    assert app_row.matched_profile == "From your resume"


def test_no_profile_and_no_readable_titles_still_skips(db):
    u = _user(db, resume="I like walking dogs and baking bread")
    _job(db, "Compliance Analyst")
    scored, result = _run(db, u)
    assert scored == [] and result["skipped_reason"] == "no_active_profiles"


def test_discovery_queries_include_resume_titles_of_profileless_users(db):
    db.query(models.User).delete()
    db.commit()
    a = _user(db)                                   # resume, no profile
    b = _user(db, resume="Nurse Practitioner\nRegistered Nurse, City Hospital 2020 - Present")
    _profile(db, b.id, ["ICU Nurse"])               # has a profile: its own titles win
    titles = pipeline_runner._collect_active_search_titles(db)
    assert "Senior IT Auditor" in titles and "ICU Nurse" in titles
    assert "Nurse Practitioner" not in titles


# --- closed postings ----------------------------------------------------

def test_posting_page_markup_and_phrases_mark_it_closed():
    assert posting_check.expired_by_markup('<script>{"validThrough":"2020-05-01T00:00"}</script>')
    assert not posting_check.expired_by_markup('{"validThrough":"2099-05-01"}')
    assert not posting_check.expired_by_markup('{"validThrough":"not a date"}')
    assert posting_check.page_says_closed("Sorry. This job is no longer open.")
    assert posting_check.page_says_closed("Job not found")


def test_job_past_its_closing_date_is_never_scored(db):
    u = _user(db)
    _profile(db, u.id, ["IT Auditor"])
    _job(db, "IT Auditor open", closes_at=datetime.utcnow() + timedelta(days=5))
    _job(db, "IT Auditor undated")
    _job(db, "IT Auditor past deadline", closes_at=datetime.utcnow() - timedelta(days=3))
    scored, _ = _run(db, u)
    assert sorted(scored) == ["IT Auditor open", "IT Auditor undated"]


def test_discovery_stores_the_usajobs_closing_date(db):
    gone = {"source": "usajobs", "external_id": "u1", "company": "Navy", "title": "IT Auditor", "location": "",
            "url": "https://usajobs.example/1", "description": "d", "closes": "2020-01-31"}
    with patch("app.services.pipeline_runner.greenhouse.fetch_all", return_value=[]), \
         patch("app.services.pipeline_runner.lever.fetch_all", return_value=[]), \
         patch("app.services.pipeline_runner.rss_boards.fetch_all", return_value=[]), \
         patch("app.services.pipeline_runner.remoteok.fetch_jobs", return_value=[]), \
         patch("app.services.pipeline_runner.arbeitnow.fetch_jobs", return_value=[]), \
         patch("app.services.pipeline_runner.adzuna.fetch_by_keywords", return_value=[]), \
         patch("app.services.pipeline_runner.adzuna.fetch_by_keyword_location_pairs", return_value=[], create=True), \
         patch("app.services.pipeline_runner.usajobs.fetch_by_keywords", return_value=[gone]):
        pipeline_runner.run_discovery(db)
    job = db.query(models.Job).filter_by(external_id="u1").one()
    assert job.closes_at == datetime(2020, 1, 31)


def _app(db, uid, job, status="pending_approval"):
    a = models.Application(user_id=uid, job_id=job.id, status=status)
    db.add(a)
    db.commit()
    return a


def test_waiting_applications_close_when_their_job_closes(db):
    u = _user(db)
    dead = _job(db, "Dead", is_active=False)
    live = _job(db, "Live")
    a1 = _app(db, u.id, dead)
    a2 = _app(db, u.id, dead, "approved")
    a3 = _app(db, u.id, dead, "submitted")
    a4 = _app(db, u.id, live)
    assert pipeline_runner.close_applications_for_closed_jobs(db) == 2
    for a in (a1, a2, a3, a4):
        db.refresh(a)
    assert [a1.status, a2.status, a3.status, a4.status] == ["closed", "closed", "submitted", "pending_approval"]
    assert "closed" in a1.notes


def test_recheck_closes_dead_jobs_skips_recent_and_respects_the_limit(db):
    u = _user(db)
    dead = _job(db, "Dead"); blocked = _job(db, "Blocked"); fresh = _job(db, "Fresh", live_checked_at=datetime.utcnow())
    extra = _job(db, "Extra")
    apps = {j.title: _app(db, u.id, j) for j in (dead, blocked, fresh, extra)}
    verdict = lambda url: False if url == dead.url else (None if url == blocked.url else True)
    with patch("app.services.pipeline_runner.posting_check.check_posting", side_effect=verdict):
        out = pipeline_runner.recheck_pending_postings(db, limit=3)
    assert out == {"checked": 3, "closed": 1, "applications_closed": 1}
    for j in (dead, blocked, fresh, extra):
        db.refresh(j)
    for a in apps.values():
        db.refresh(a)
    assert dead.is_active is False and apps["Dead"].status == "closed"
    assert blocked.live_checked_at is None            # couldn't tell: asked again next time
    assert apps["Fresh"].status == "pending_approval"  # checked recently, not looked at again


def _as(uid):
    def _u(db=Depends(get_db)):
        return db.get(models.User, uid)
    app.dependency_overrides[get_current_user] = _u
    return TestClient(app)


def test_near_misses_and_list_hide_closed_jobs(db):
    u = _user(db)
    live = _job(db, "Live"); dead = _job(db, "Dead", is_active=False)
    for j in (live, dead):
        db.add(models.NearMissResult(user_id=u.id, job_id=j.id, score=50, reason="r", matched_profile="P"))
    a = _app(db, u.id, dead)
    db.commit()
    c = _as(u.id)
    assert [n["title"] for n in c.get("/pipeline/near-misses").json()] == ["Live"]
    row = [r for r in c.get("/applications").json() if r["id"] == a.id][0]
    assert row["job_open"] is False


def test_approve_checks_the_posting_first(db):
    u = _user(db)
    open_job = _job(db, "Open"); dead_page = _job(db, "DeadPage"); flagged = _job(db, "Flagged", is_active=False)
    ok, dead, gone = _app(db, u.id, open_job), _app(db, u.id, dead_page), _app(db, u.id, flagged)
    c = _as(u.id)
    with patch("app.routers.pipeline.posting_check.check_posting",
               side_effect=lambda url: False if url == dead_page.url else True):
        assert c.post(f"/applications/{ok.id}/approve").status_code == 200
        r = c.post(f"/applications/{dead.id}/approve")
        assert r.status_code == 409 and "closed" in r.json()["detail"]
        assert c.post(f"/applications/{gone.id}/approve").status_code == 409
    for a in (ok, dead, gone):
        db.refresh(a)
    assert (ok.status, dead.status, gone.status) == ("approved", "closed", "closed")
    db.refresh(dead_page)
    assert dead_page.is_active is False      # nobody else is matched to it either


def test_approve_keeps_the_job_when_the_site_will_not_say(db):
    u = _user(db)
    j = _job(db, "Blocked"); a = _app(db, u.id, j)
    with patch("app.routers.pipeline.posting_check.check_posting", return_value=None):
        assert _as(u.id).post(f"/applications/{a.id}/approve").status_code == 200


# --- regression: the relevance check must not hide jobs people want ------

@pytest.mark.parametrize("profile_title, wanted_jobs", [
    ("Cybersecurity Architect", ["Security Architect", "Information Security Engineer", "Cloud Security Lead", "Cyber Defense Analyst"]),
    ("IT Auditor", ["Internal Audit Manager", "Technology Risk Assurance Associate", "Information Systems Auditor"]),
    ("Project Scheduler", ["Planning Engineer", "Primavera P6 Planner", "Construction Project Controls Specialist"]),
    ("Software Engineer", ["Backend Developer", "Python Developer", "Full Stack Developer"]),
    ("Registered Nurse", ["RN - Medical Surgical", "Staff Nurse ICU", "Clinical Nurse II"]),
])
def test_related_job_names_are_not_hidden(profile_title, wanted_jobs):
    p = [{"titles": [profile_title], "keywords_required": [], "keywords_excluded": [], "active": True}]
    for title in wanted_jobs:
        assert search_terms.title_fits(title, p), f"{title!r} was hidden from a {profile_title!r} search"


def test_the_start_of_the_description_can_rescue_an_unusual_title():
    p = [{"titles": ["IT Auditor"], "keywords_required": [], "keywords_excluded": [], "active": True}]
    assert not search_terms.title_fits("SOX Compliance Analyst", p)
    assert search_terms.title_fits("SOX Compliance Analyst", p, "You will support our internal audit team on SOX testing")
    assert not search_terms.title_fits("Sales Manager", p, "Grow revenue across the region")


def test_the_relevance_check_can_be_switched_off(db):
    from app.config import settings
    u = _user(db)
    _profile(db, u.id, ["IT Auditor"])
    _job(db, "Sales Manager")
    old = settings.match_relevance_check
    settings.match_relevance_check = False
    try:
        scored, _ = _run(db, u)
    finally:
        settings.match_relevance_check = old
    assert scored == ["Sales Manager"]


def test_a_job_is_kept_when_only_its_description_matches(db):
    u = _user(db)
    _profile(db, u.id, ["IT Auditor"])
    _job(db, "SOX Compliance Analyst", description="Support our internal audit team")
    _job(db, "Sales Manager", description="Grow revenue")
    scored, result = _run(db, u)
    assert scored == ["SOX Compliance Analyst"] and result["off_target"] == 1


def test_find_new_matches_works_with_a_resume_and_no_profile(db):
    u = _user(db)
    c = _as(u.id)
    with patch("app.services.pipeline_runner.run_single_user_matching_background"):
        assert c.post("/pipeline/match").status_code == 202
    bare = _user(db, resume="I like walking dogs and baking bread")
    r = _as(bare.id).post("/pipeline/match")
    assert r.status_code == 400 and "search profile" in r.json()["detail"]
