"""
Pulls open roles from Greenhouse's public job board API.
No auth required. Find a company's slug from their careers URL:
https://boards.greenhouse.io/<slug>
"""
import requests

API_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"

# Some hosts block requests with no User-Agent (or a default
# "python-requests/x.x" one) as basic bot mitigation -- see the longer
# note in rss_boards.py. Same realistic browser-style UA for consistency.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_jobs(company_slug: str):
    """Returns a list of normalized job dicts for one company."""
    resp = requests.get(API_URL.format(company=company_slug), timeout=20, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "source": "greenhouse",
            "external_id": str(j["id"]),
            "company": company_slug,
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": j.get("content", ""),  # HTML
        })
    return jobs


def fetch_all(company_slugs: list[str]):
    all_jobs = []
    for slug in company_slugs:
        try:
            all_jobs.extend(fetch_jobs(slug))
        except requests.RequestException as e:
            print(f"[greenhouse] failed for {slug}: {e}")
    return all_jobs
