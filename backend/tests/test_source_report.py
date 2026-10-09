"""Discovery reports what each job source did, and Admin shows it."""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal, get_db
from app import models
from app.security import get_current_user, get_current_admin
from app.services import pipeline_runner
from app.services.sources import report


@pytest.fixture()
def db():
    s = SessionLocal()
    s.query(models.Job).delete()
    s.query(models.ScheduledRunLog).delete()
    s.commit()
    yield s
    s.close()
    app.dependency_overrides.clear()


def _job(source, n):
    return {"source": source, "external_id": f"{source}-{n}", "company": "Acme", "title": "Auditor",
            "location": "Remote", "url": f"https://x.example/{source}/{n}", "description": "d"}


def _run_discovery(db, **fakes):
    base = {
        "greenhouse.fetch_all": [], "lever.fetch_all": [], "rss_boards.fetch_all": [],
        "remoteok.fetch_jobs": [], "arbeitnow.fetch_jobs": [], "adzuna.fetch_by_keywords": [],
        "adzuna.fetch_by_keyword_location_pairs": [], "usajobs.fetch_by_keywords": [],
    }
    base.update(fakes)
    patches = []
    for target, value in base.items():
        fn = value if callable(value) else (lambda *a, _v=value, **k: _v)
        patches.append(patch(f"app.services.pipeline_runner.{target}", side_effect=fn, create=True))
    for p in patches:
        p.start()
    try:
        return pipeline_runner.run_discovery(db)
    finally:
        for p in patches:
            p.stop()


def test_each_source_reports_what_it_did_and_why_it_returned_nothing(db):
    def blocked_rss(urls):
        report.problem("rss", "https://feed.example/jobs: 403 Forbidden")
        return []

    def keyless_adzuna(keywords):
        report.not_configured("adzuna", "ADZUNA_APP_ID and ADZUNA_APP_KEY")
        return []

    result = _run_discovery(db, **{
        "greenhouse.fetch_all": [_job("greenhouse", i) for i in range(3)],
        "rss_boards.fetch_all": blocked_rss,
        "adzuna.fetch_by_keywords": keyless_adzuna,
    })
    by_name = {s["name"]: s for s in result["sources"]}
    assert by_name["greenhouse"]["status"] == "ok" and by_name["greenhouse"]["fetched"] == 3 and by_name["greenhouse"]["new"] == 3
    assert by_name["rss"]["status"] == "failed" and "403" in by_name["rss"]["notes"][0]
    assert by_name["adzuna"]["status"] == "not_configured" and "ADZUNA_APP_ID" in by_name["adzuna"]["notes"][0]
    assert by_name["remoteok"]["status"] == "empty" and by_name["remoteok"]["notes"] == []
    assert set(by_name) == {"greenhouse", "lever", "rss", "remoteok", "arbeitnow", "adzuna", "usajobs", "adzuna_location"}
    assert result["discovered"] == 3 and result["new"] == 3


def test_a_sources_notes_do_not_leak_into_the_next_run(db):
    report.problem("lever", "left over")
    report.take("lever")
    result = _run_discovery(db)
    assert {s["name"]: s for s in result["sources"]}["lever"]["notes"] == []


def test_a_source_with_some_failures_but_results_is_still_ok_with_notes(db):
    def partial(slugs):
        report.problem("greenhouse", "badco: 404")
        return [_job("greenhouse", 1)]
    result = _run_discovery(db, **{"greenhouse.fetch_all": partial})
    gh = {s["name"]: s for s in result["sources"]}["greenhouse"]
    assert gh["status"] == "ok" and gh["notes"] == ["badco: 404"]


def _admin(db):
    u = models.User(email=f"adm{uuid.uuid4().hex[:6]}@x.com", hashed_password="x", is_admin=True, admin_role="super")
    db.add(u)
    db.commit()
    def _u(d=Depends(get_db)):
        return d.get(models.User, u.id)
    app.dependency_overrides[get_current_user] = _u
    app.dependency_overrides[get_current_admin] = _u
    return TestClient(app)


def test_admin_health_shows_every_source_the_last_run_and_what_needs_fixing(db):
    now = datetime.utcnow()
    db.add_all([
        models.Job(source="greenhouse", external_id="1", title="a", discovered_at=now - timedelta(days=20), last_seen_at=now),
        models.Job(source="greenhouse", external_id="2", title="b", discovered_at=now - timedelta(days=20), last_seen_at=now, is_active=False),
        models.Job(source="arbeitnow", external_id="1", title="c", discovered_at=now - timedelta(days=30), last_seen_at=now - timedelta(days=30)),
    ])
    sources = [
        {"name": "greenhouse", "status": "ok", "fetched": 2, "new": 0, "detail": "", "notes": []},
        {"name": "remoteok", "status": "failed", "fetched": 0, "new": 0, "detail": "", "notes": ["Fetch failed: 403"]},
    ]
    db.add(models.ScheduledRunLog(run_type="interactive_discover", status="success", finished_at=now,
                                  result_json=json.dumps({"discovered": 2, "new": 0, "sources": sources})))
    db.commit()
    client = _admin(db)
    with patch.object(settings, "adzuna_app_id", ""), patch.object(settings, "usajobs_api_key", ""):
        body = client.get("/admin/system-health").json()

    by = {s["source"]: s for s in body["job_sources"]}
    # a source that keeps seeing the same jobs is healthy, even though nothing is new
    assert by["greenhouse"]["status"] == "healthy" and by["greenhouse"]["jobs_last_24h"] == 0
    assert by["greenhouse"]["active_jobs"] == 1
    assert by["arbeitnow"]["status"] == "silent"
    # sources with no jobs at all are still listed
    assert {"remoteok", "adzuna", "usajobs", "lever"} <= set(by)
    assert body["total_jobs_in_pool"] == 3 and body["active_jobs_in_pool"] == 2
    assert [r["name"] for r in body["last_discovery"]] == ["greenhouse", "remoteok"]
    joined = " ".join(body["warnings"])
    assert "Adzuna" in joined and "ADZUNA_APP_ID" in joined and "USAJobs" in joined
    assert "remoteok returned nothing" in joined and "403" in joined


def test_admin_health_works_before_any_run_has_been_recorded(db):
    body = _admin(db).get("/admin/system-health").json()
    assert body["last_discovery"] == [] and body["last_discovery_at"] is None


def test_scheduled_run_results_are_read_too(db):
    sources = [{"name": "lever", "status": "ok", "fetched": 5, "new": 5, "detail": "", "notes": []}]
    db.add(models.ScheduledRunLog(run_type="scheduled_run", status="success", finished_at=datetime.utcnow(),
                                  result_json=json.dumps({"discovery": {"discovered": 5, "new": 5, "sources": sources}, "users_processed": 0})))
    db.commit()
    body = _admin(db).get("/admin/system-health").json()
    assert [r["name"] for r in body["last_discovery"]] == ["lever"] and body["last_discovery_kind"] == "scheduled_run"


# --- email delivery -------------------------------------------------------

def _email_logs(db):
    return db.query(models.EmailLog).order_by(models.EmailLog.id).all()


def test_email_attempts_are_recorded_with_the_reason(db):
    from app.services import notifier
    db.query(models.EmailLog).delete()
    db.commit()

    with patch.object(settings, "resend_api_key", ""):
        assert notifier.send_email("a@x.com", "Hello", "body", kind="welcome") == "skipped"

    import resend
    with patch.object(settings, "resend_api_key", "re_test"), patch.object(resend.Emails, "send", return_value={"id": "1"}):
        assert notifier.send_email("b@x.com", "Hi", "body", kind="new_match") == "sent"

    with patch.object(settings, "resend_api_key", "re_test"), \
         patch.object(resend.Emails, "send", side_effect=Exception("The riseply.com domain is not verified")):
        with pytest.raises(Exception, match="not verified"):
            notifier.send_email("c@x.com", "Hi", "body", kind="digest")

    rows = _email_logs(db)
    assert [(r.kind, r.status) for r in rows] == [("welcome", "skipped"), ("new_match", "sent"), ("digest", "failed")]
    assert "RESEND_API_KEY" in rows[0].error and "not verified" in rows[2].error
    assert "body" not in " ".join(r.subject + r.error for r in rows)   # never the message body


def test_a_rate_limited_send_is_retried(db):
    from app.services import notifier
    import resend
    calls = []
    def flaky(params):
        calls.append(1)
        if len(calls) < 3:
            raise Exception("Too many requests. You can only make 2 requests per second.")
        return {"id": "ok"}
    with patch.object(settings, "resend_api_key", "re_test"), patch.object(resend.Emails, "send", side_effect=flaky), \
         patch("time.sleep") as nap:
        assert notifier.send_email("a@x.com", "s", "b") == "sent"
    assert len(calls) == 3 and nap.call_count == 2


def test_admin_email_health_and_test_button(db):
    import resend
    db.query(models.EmailLog).delete()
    db.commit()
    client = _admin(db)

    with patch.object(settings, "resend_api_key", ""):
        health = client.get("/admin/email-health").json()
        assert health["configured"] is False
        warn = " ".join(client.get("/admin/system-health").json()["warnings"])
        assert "RESEND_API_KEY" in warn
        t = client.post("/admin/email-test").json()
        assert t["ok"] is False and "RESEND_API_KEY" in t["detail"]

    with patch.object(settings, "resend_api_key", "re_test"):
        with patch.object(resend.Emails, "send", side_effect=Exception("domain not verified")):
            t = client.post("/admin/email-test").json()
            assert t["ok"] is False and "domain not verified" in t["detail"]
        with patch.object(resend.Emails, "send", return_value={"id": "1"}):
            t = client.post("/admin/email-test").json()
            assert t["ok"] is True
        health = client.get("/admin/email-health").json()
        assert health["configured"] is True
        assert (health["sent_24h"], health["failed_24h"], health["skipped_24h"]) == (1, 1, 1)
        assert {p["status"] for p in health["recent_problems"]} == {"failed", "skipped"}
        assert "RESEND_API_KEY" not in " ".join(client.get("/admin/system-health").json()["warnings"])
