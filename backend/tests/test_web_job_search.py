"""JSearch and Jooble: web-wide job search that follows people's search profiles."""
from unittest.mock import MagicMock, patch

from app.config import settings
from app.services.sources import jooble, jsearch, report


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_both_sources_do_nothing_and_say_so_without_a_key(monkeypatch):
    monkeypatch.setattr(settings, "jsearch_api_key", "")
    monkeypatch.setattr(settings, "jooble_api_key", "")
    with patch("requests.get") as g, patch("requests.post") as p:
        assert jsearch.fetch_by_queries([("Auditor", "Chicago")]) == []
        assert jooble.fetch_by_queries([("Auditor", "Chicago")]) == []
    assert not g.called and not p.called
    assert report.take("jsearch")[1] and report.take("jooble")[1]


def test_jsearch_maps_a_result_and_asks_for_title_in_place(monkeypatch):
    monkeypatch.setattr(settings, "jsearch_api_key", "k")
    data = {"data": [
        {"job_id": "abc", "job_title": "IT Auditor", "employer_name": "Acme", "job_city": "Chicago",
         "job_state": "IL", "job_country": "US", "job_apply_link": "https://acme.example/apply",
         "job_description": "Audit things", "job_min_salary": 90000.4, "job_max_salary": 120000,
         "job_salary_currency": "USD", "job_posted_at_datetime_utc": "2026-11-10T12:00:00.000Z"},
        {"job_id": "nolink", "job_title": "X"},
    ]}
    with patch("requests.get", return_value=_resp(data)) as g:
        jobs = jsearch.fetch_by_queries([("IT Auditor", "Chicago, IL")])
    assert g.call_args.kwargs["params"]["query"] == "IT Auditor in Chicago, IL"
    assert g.call_args.kwargs["headers"]["X-RapidAPI-Key"] == "k"
    assert len(jobs) == 1
    j = jobs[0]
    assert j["source"] == "jsearch" and j["external_id"] == "abc" and j["location"] == "Chicago, IL, US"
    assert j["salary_min"] == 90000 and j["salary_currency"] == "USD" and j["url"].startswith("https://acme")


def test_jsearch_marks_remote_and_survives_a_failed_query(monkeypatch):
    import requests
    monkeypatch.setattr(settings, "jsearch_api_key", "k")
    remote = {"data": [{"job_id": "r1", "job_title": "Analyst", "job_is_remote": True,
                        "job_apply_link": "https://x.example/r1"}]}
    with patch("requests.get", side_effect=[requests.ConnectionError("down"), _resp(remote)]):
        jobs = jsearch.fetch_by_queries([("A", ""), ("B", "")])
    assert [j["location"] for j in jobs] == ["Remote"]
    assert any("Request failed" in n for n in report.take("jsearch")[0])


def test_jooble_maps_results_hashes_missing_ids_and_hides_its_key(monkeypatch):
    import requests
    monkeypatch.setattr(settings, "jooble_api_key", "SECRETKEY")
    data = {"jobs": [{"title": "Compliance Analyst", "company": "Beta", "location": "Remote",
                      "link": "https://beta.example/j/1", "snippet": "Do compliance", "updated": "2026-11-10"}]}
    with patch("requests.post", return_value=_resp(data)) as p:
        jobs = jooble.fetch_by_queries([("Compliance Analyst", "")])
    assert p.call_args.args[0].endswith("/SECRETKEY") and p.call_args.kwargs["json"]["keywords"] == "Compliance Analyst"
    assert jobs[0]["source"] == "jooble" and len(jobs[0]["external_id"]) == 20
    with patch("requests.post", side_effect=requests.ConnectionError("failed https://jooble.org/api/SECRETKEY")):
        assert jooble.fetch_by_queries([("A", "")]) == []
    notes = " ".join(report.take("jooble")[0])
    assert "SECRETKEY" not in notes and "***" in notes


def test_discovery_sends_profile_titles_and_places_to_both_sources():
    from app.database import SessionLocal
    from app.services import pipeline_runner
    seen = {}
    names = ["greenhouse.fetch_all", "lever.fetch_all", "rss_boards.fetch_all", "remoteok.fetch_jobs",
             "arbeitnow.fetch_jobs", "adzuna.fetch_by_keywords", "adzuna.fetch_by_keyword_location_pairs",
             "usajobs.fetch_by_keywords"]
    ps = [patch(f"app.services.pipeline_runner.{n}", return_value=[], create=True) for n in names]
    ps.append(patch("app.services.pipeline_runner.jsearch.fetch_by_queries",
                    side_effect=lambda pairs: seen.setdefault("js", pairs) and []))
    ps.append(patch("app.services.pipeline_runner.jooble.fetch_by_queries",
                    side_effect=lambda pairs: seen.setdefault("jo", pairs) and []))
    ps.append(patch("app.services.pipeline_runner._collect_active_search_titles", return_value=["Auditor", "Analyst"]))
    ps.append(patch("app.services.pipeline_runner._collect_active_location_hints", return_value=["Chicago, IL"]))
    for p in ps:
        p.start()
    db = SessionLocal()
    try:
        out = pipeline_runner.run_discovery(db)
    finally:
        for p in ps:
            p.stop()
        db.close()
    assert seen["js"] == [("Auditor", "Chicago, IL"), ("Analyst", "Chicago, IL")] == seen["jo"]
    assert {"jsearch", "jooble"} <= {s["name"] for s in out["sources"]}
