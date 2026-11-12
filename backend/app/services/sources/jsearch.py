"""
Searches the wider web for jobs through JSearch (RapidAPI), which gathers
Google for Jobs results: postings from LinkedIn, Indeed, Glassdoor,
ZipRecruiter and company career pages. This is the "search the internet"
source: it follows the titles and places people actually put in their
search profiles instead of a fixed company list.

Needs a RapidAPI key with the JSearch API subscribed (see app/config.py).
Until JSEARCH_API_KEY is set it does nothing, like every other optional
integration here. Each query is one API call, so discovery caps how many it
sends per run (jsearch_max_queries_per_run).
"""
import requests

from app.config import settings
from app.services.sources import report

API_URL = "https://jsearch.p.rapidapi.com/search"
HOST = "jsearch.p.rapidapi.com"


def _location(j: dict) -> str:
    parts = [j.get("job_city"), j.get("job_state"), j.get("job_country")]
    place = ", ".join(p for p in parts if p)
    if j.get("job_is_remote"):
        return f"Remote ({place})" if place else "Remote"
    return place


def normalize(j: dict) -> dict | None:
    """One JSearch result in the shape run_discovery() expects, or None when
    it has no id or no link to apply through."""
    ext = str(j.get("job_id") or "")
    url = j.get("job_apply_link") or j.get("job_google_link") or ""
    if not ext or not url:
        return None
    lo, hi = j.get("job_min_salary"), j.get("job_max_salary")
    return {
        "source": "jsearch",
        "external_id": ext,
        "company": j.get("employer_name") or "",
        "title": j.get("job_title") or "",
        "location": _location(j),
        "url": url,
        "description": j.get("job_description") or "",
        "posted": j.get("job_posted_at_datetime_utc"),
        "salary_min": round(lo) if lo else None,
        "salary_max": round(hi) if hi else None,
        "salary_currency": (j.get("job_salary_currency") or "USD") if (lo or hi) else "",
        "salary_is_predicted": False,
    }


def fetch_query(keyword: str, location: str = "") -> list[dict]:
    query = f"{keyword} in {location}" if location else keyword
    try:
        resp = requests.get(
            API_URL,
            headers={"X-RapidAPI-Key": settings.jsearch_api_key, "X-RapidAPI-Host": HOST},
            params={"query": query, "page": 1, "num_pages": 1, "date_posted": "week"},
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or []
    except (requests.RequestException, ValueError) as e:
        body = getattr(getattr(e, "response", None), "text", "")[:200]
        print(f"[jsearch] failed for {query!r}: {e} {body}")
        report.problem("jsearch", f"Request failed for {query!r}: {e} {body}")
        return []
    jobs = [n for n in (normalize(j) for j in data) if n]
    print(f"[jsearch] {query!r}: {len(jobs)} postings")
    return jobs


def fetch_by_queries(pairs: list[tuple[str, str]]) -> list[dict]:
    """(title, place) pairs; a blank place searches the title everywhere.
    One failing query never costs the others."""
    if not settings.jsearch_api_key:
        print("[jsearch] skipped -- JSEARCH_API_KEY not set")
        report.not_configured("jsearch", "JSEARCH_API_KEY")
        return []
    if not pairs:
        report.problem("jsearch", "No job titles to search for yet (no search profiles or resume titles).")
        return []
    out = []
    for kw, loc in pairs:
        try:
            out.extend(fetch_query(kw, loc))
        except Exception as e:  # noqa: BLE001 - one bad query must not stop the run
            report.problem("jsearch", f"Error for ({kw!r}, {loc!r}): {e}")
    return out
