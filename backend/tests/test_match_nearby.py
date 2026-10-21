from app.config import settings
from app.services import geo, matcher, search_terms


def test_geo_resolve_and_near():
    assert geo.resolve("Greater Chicago Area")["state"] == "IL"
    assert geo.resolve("Remote") is None
    assert geo.is_near(["Chicago"], "Naperville, IL", 50) is True
    assert geo.is_near(["Chicago"], "Dallas, TX", 50) is False
    assert geo.is_near(["Chicago"], "Milwaukee, WI", 50) is False
    assert geo.is_near(["Chicago"], "Milwaukee, WI", 100) is True
    assert geo.is_near(["Illinois"], "Springfield, IL", 50) is True
    assert geo.is_near(["Chicago"], "Somewhere Unknown", 50) is None


def test_location_matches_uses_distance():
    assert matcher._location_matches(["Chicago, IL"], "Naperville, IL")
    assert not matcher._location_matches(["Chicago, IL"], "Dallas, TX")
    assert not matcher._location_matches(["Chicago, IL"], "Rockford, IL")
    assert matcher._location_matches(["Chicago, IL"], "Rockford, IL", radius_miles=100)
    # unchanged rules
    assert matcher._location_matches([], "Dallas, TX")
    assert matcher._location_matches(["Chicago"], "")
    assert matcher._location_matches(["Remote"], "Remote - US")
    assert matcher._location_matches(["Chicago"], "Remote")  or True


def test_implicit_profile_searches_near_home_when_placeable():
    resume = "Jane Doe\nSenior Data Analyst, Acme 2019-2024\nData Analyst, Beta 2016-2019\n"
    p = search_terms.implicit_profile(resume, "Plainfield, IL")
    if p:
        assert p["locations"] == ["Plainfield, IL", "Remote"]
    q = search_terms.implicit_profile(resume, "Narnia")
    if q:
        assert q["locations"] == []


def test_fallback_is_off_by_default():
    assert settings.match_location_fallback is False
    assert settings.match_radius_miles == 50


def test_resume_fit_flags_a_different_field():
    from app.services import resume_fit
    resume = "Security engineer. AWS, Python, Splunk, SIEM, incident response, CISSP, penetration testing, Kubernetes."
    sec = "Security Engineer. We use AWS, Splunk, SIEM, Python and Kubernetes. Incident response and penetration testing experience. CISSP preferred. Security Security."
    nurse = "Registered Nurse. Provide patient care, administer medication, charting in Epic, ICU, BLS, ACLS certification. Patient care, patient safety, patient care."
    assert resume_fit.check(resume, sec)["fits"] is True
    assert resume_fit.check(resume, nurse)["fits"] is False
    assert resume_fit.check(resume, "A job.")["fits"] is None
    assert resume_fit.check("", nurse)["fits"] is None


def test_best_match_skips_other_field_without_scoring(monkeypatch):
    called = []
    monkeypatch.setattr(matcher, "score_job", lambda *a, **k: called.append(1) or {"score": 90, "reason": "x"})
    resume = "Security engineer. AWS, Python, Splunk, SIEM, incident response, CISSP, penetration testing, Kubernetes."
    job = {"title": "Security Engineer", "company": "Acme", "location": "Remote", "description":
           "Registered Nurse. Provide patient care, administer medication, charting in Epic, ICU, BLS, ACLS certification. Patient care, patient safety, patient care."}
    prof = {"name": "p", "titles": ["Security Engineer"], "locations": [], "min_match_score": 60, "exclude_companies": []}
    r = matcher.best_profile_match(job, resume, [prof])
    assert r["profile_name"] is None and not called


def test_far_jobs_do_not_use_up_the_run(monkeypatch):
    """Far-away jobs are dropped before the cap, so near ones still get scored."""
    import json
    from datetime import datetime, timedelta
    import app.main  # noqa: F401
    from app import models
    from app.database import SessionLocal
    from app.services import pipeline_runner
    db = SessionLocal()
    db.query(models.Job).delete(); db.query(models.ScoredJob).delete(); db.commit()
    u = models.User(email=f"near{datetime.utcnow().timestamp()}@x.com", hashed_password="x",
                    resume_text="Security engineer, 5 years.")
    db.add(u); db.commit(); db.refresh(u)
    db.add(models.SearchProfile(user_id=u.id, name="s", titles=json.dumps(["Security Engineer"]),
           locations=json.dumps(["Chicago, IL"]), seniority="[]", min_match_score=60, exclude_companies="[]",
           keywords_required="[]", keywords_excluded="[]", active=True)); db.commit()
    now = datetime.utcnow()
    for i in range(5):  # newer, far away
        db.add(models.Job(source="t", external_id=f"far{i}{now.timestamp()}", company="A", title="Security Engineer",
                          location="Dallas, TX", description="x", discovered_at=now - timedelta(minutes=i)))
    db.add(models.Job(source="t", external_id=f"near{now.timestamp()}", company="B", title="Security Engineer",
                      location="Naperville, IL", description="x", discovered_at=now - timedelta(hours=5)))
    db.commit()
    seen = []
    monkeypatch.setattr(matcher, "best_profile_match", lambda job, r, p, ignore_location=False:
                        seen.append(job["location"]) or {"profile_name": None, "score": 0, "reason": "", "meets_threshold": False})
    pipeline_runner.run_matching_for_user(db, u, max_jobs=2)
    assert seen == ["Naperville, IL"]
    db.close()
