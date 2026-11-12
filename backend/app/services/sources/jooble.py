"""
Searches Jooble, a job search engine that gathers postings from thousands of
sites worldwide. Keyword and place driven, like jsearch.py and adzuna.py.

Needs a free API key from https://jooble.org/api/about (see app/config.py).
Until JOOBLE_API_KEY is set it does nothing.
"""
import hashlib

import requests

from app.config import settings
from app.services.sources import report

API_URL = "https://jooble.org/api/{key}"


def normalize(j: dict) -> dict | None:
    url = j.get("link") or ""
    title = j.get("title") or ""
    if not url or not title:
        return None
    ext = str(j.get("id") or "") or hashlib.sha1(url.encode()).hexdigest()[:20]
    return {
        "source": "jooble",
        "external_id": ext,
        "company": j.get("company") or "",
        "title": title,
        "location": j.get("location") or "",
        "url": url,
        "description": j.get("snippet") or "",
        "posted": j.get("updated"),
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "",
        "salary_is_predicted": False,
    }


def fetch_query(keyword: str, location: str = "") -> list[dict]:
    body = {"keywords": keyword, "location": location, "page": 1}
    try:
        resp = requests.post(API_URL.format(key=settings.jooble_api_key), json=body, timeout=25)
        resp.raise_for_status()
        data = resp.json().get("jobs") or []
    except (requests.RequestException, ValueError) as e:
        # The key is part of the URL, so keep it out of anything we log.
        msg = str(e).replace(settings.jooble_api_key, "***")
        print(f"[jooble] failed for {keyword!r}: {msg}")
        report.problem("jooble", f"Request failed for {keyword!r}: {msg}")
        return []
    jobs = [n for n in (normalize(j) for j in data) if n]
    print(f"[jooble] {keyword!r} / {location!r}: {len(jobs)} postings")
    return jobs


def fetch_by_queries(pairs: list[tuple[str, str]]) -> list[dict]:
    if not settings.jooble_api_key:
        print("[jooble] skipped -- JOOBLE_API_KEY not set")
        report.not_configured("jooble", "JOOBLE_API_KEY")
        return []
    if not pairs:
        report.problem("jooble", "No job titles to search for yet (no search profiles or resume titles).")
        return []
    out = []
    for kw, loc in pairs:
        try:
            out.extend(fetch_query(kw, loc))
        except Exception as e:  # noqa: BLE001
            report.problem("jooble", f"Error for ({kw!r}, {loc!r}): {e}")
    return out
