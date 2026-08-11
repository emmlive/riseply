"""
Pulls postings from Adzuna's public job search API -- a general aggregator
covering every industry (retail, healthcare, finance, compliance/audit,
legal, etc), not just tech. This is deliberately different in shape from
greenhouse.py/lever.py: those pull ALL open roles for a fixed, hand-picked
list of companies (which only works if you already know which companies
are relevant); this pulls by KEYWORD, so it follows whatever titles users
are actually searching for instead of being capped by a hardcoded list.

Requires a free app_id/app_key pair from https://developer.adzuna.com/ --
until both are set (see app/config.py), fetch_by_keywords() no-ops, same
kill-switch pattern as every other optional integration in this codebase
(Resend, Twilio, Stripe).

Free tier is ~1,000 calls/month (per Adzuna's published limits as of this
writing -- reconfirm on developer.adzuna.com if this ever needs raising).
One call = one page of up to RESULTS_PER_PAGE results for one keyword, so
discovery deliberately caps how many distinct keywords it queries per run
(see MAX_KEYWORDS_PER_RUN below and its use in pipeline_runner.py) rather
than looping over every keyword every user has ever entered -- that alone
could burn the whole monthly quota in a single run once there are more
than a handful of active search profiles.
"""
import requests

from app.config import settings

# US only for now -- Adzuna supports ~20 country indexes (co.uk, com.au,
# etc), but this product's user base and the discovery_sources.py sources
# it complements (Greenhouse/Lever/RSS) are all US-centric today. Revisit
# if Riseply ever supports non-US job seekers.
API_URL = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"

RESULTS_PER_PAGE = 50
# How many pages to pull per keyword per run. Kept small on purpose --
# multiplies directly against the monthly call budget (keywords x pages),
# and the goal here is broad keyword COVERAGE across many different
# search profiles, not exhaustive depth on any single one.
PAGES_PER_KEYWORD = 1


def fetch_jobs_for_keyword(keyword: str, location: str = "") -> list[dict]:
    """One keyword, up to PAGES_PER_KEYWORD pages. Returns normalized job
    dicts in the same shape run_discovery() already expects from every
    other source (see greenhouse.py for the reference shape)."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        return []

    jobs = []
    for page in range(1, PAGES_PER_KEYWORD + 1):
        params = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what": keyword,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location

        try:
            resp = requests.get(API_URL.format(page=page), params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[adzuna] failed for keyword {keyword!r} page {page}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break  # ran out of pages for this keyword -- no point requesting further pages

        for j in results:
            company = (j.get("company") or {}).get("display_name", "")
            location_name = (j.get("location") or {}).get("display_name", "")
            jobs.append({
                # "adzuna" alone (not per-keyword) as the source name --
                # the same real posting can legitimately surface under
                # several different keyword searches (e.g. both "auditor"
                # and "compliance analyst" queries can return the same
                # job), and the (source, external_id) uniqueness
                # constraint in run_discovery() needs a STABLE key across
                # those repeat sightings so it dedupes into one Job row,
                # not one per keyword it happened to match.
                "source": "adzuna",
                "external_id": str(j.get("id", "")),
                "company": company,
                "title": j.get("title", ""),
                "location": location_name,
                "url": j.get("redirect_url", ""),
                "description": j.get("description", ""),
            })

    return jobs


def fetch_by_keywords(keywords: list[str]) -> list[dict]:
    """Fetches for several keywords and flattens the results. Per-keyword
    failures (a bad query, a transient 5xx) don't abort the rest -- one
    keyword erroring out shouldn't cost discovery every OTHER keyword's
    results in the same run."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        return []

    all_jobs = []
    for kw in keywords:
        try:
            all_jobs.extend(fetch_jobs_for_keyword(kw))
        except Exception as e:
            print(f"[adzuna] unexpected error for keyword {kw!r}: {e}")
    return all_jobs
