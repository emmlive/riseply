"""
Pulls open roles from Lever's public postings API.
No auth required. Find a company's slug from their careers URL:
https://jobs.lever.co/<slug>
"""
import requests

API_URL = "https://api.lever.co/v0/postings/{company}?mode=json"

# Same reasoning as greenhouse.py / rss_boards.py -- a bare Python
# requests UA gets blocked by some hosts as basic bot mitigation.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_jobs(company_slug: str):
    resp = requests.get(API_URL.format(company=company_slug), timeout=20, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for j in data:
        cat = j.get("categories", {}) or {}
        jobs.append({
            "source": "lever",
            "external_id": j.get("id", ""),
            "company": company_slug,
            "title": j.get("text", ""),
            "location": cat.get("location", ""),
            "url": j.get("hostedUrl", ""),
            "description": j.get("descriptionPlain", j.get("description", "")),
        })
    return jobs


def fetch_all(company_slugs: list[str]):
    all_jobs = []
    for slug in company_slugs:
        try:
            all_jobs.extend(fetch_jobs(slug))
        except requests.RequestException as e:
            print(f"[lever] failed for {slug}: {e}")
    return all_jobs
