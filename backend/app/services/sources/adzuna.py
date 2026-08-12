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


def fetch_jobs_for_keyword(keyword: str, location: str = "") -> list[dict]:
    """One keyword, up to settings.adzuna_pages_per_keyword pages. Returns
    normalized job dicts in the same shape run_discovery() already
    expects from every other source (see greenhouse.py for the
    reference shape)."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        # Deliberately loud (not just a silent []) -- a credentials-unset
        # skip and a "made the call, got zero results" outcome look
        # IDENTICAL from the outside (both return no new jobs, no
        # exception), which made a real production issue undiagnosable
        # from the logs alone. This print is the only thing that tells
        # the two apart after the fact.
        print("[adzuna] skipped -- ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
        return []

    jobs = []
    for page in range(1, settings.adzuna_pages_per_keyword + 1):
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
            # resp.text (when a response actually came back, e.g. a 401
            # for a bad key pair) carries Adzuna's own error message --
            # str(e) alone typically only shows the status code and URL,
            # not WHY it was rejected, which is exactly the detail
            # needed to tell "bad credentials" apart from "Adzuna is
            # down" apart from "malformed request".
            body = getattr(e, "response", None)
            body_text = body.text[:300] if body is not None else "(no response body)"
            print(f"[adzuna] failed for keyword {keyword!r} page {page}: {e} -- body: {body_text}")
            break

        results = data.get("results", [])
        print(f"[adzuna] keyword {keyword!r} page {page}: {len(results)} results")
        if not results:
            break  # ran out of pages for this keyword -- no point requesting further pages

        for j in results:
            company = (j.get("company") or {}).get("display_name", "")
            location_name = (j.get("location") or {}).get("display_name", "")
            # salary_min/salary_max are floats in Adzuna's response even
            # though real-world salaries are always whole numbers --
            # rounding to int here keeps the Job model's columns simple
            # ints and avoids showing a person "$85432.18787" instead of
            # "$85,432". Adzuna only returns these two fields when it
            # actually has a number to give (stated or modeled) --
            # .get() with None default preserves that "no data" signal
            # rather than coercing a missing salary into a misleading 0.
            salary_min = j.get("salary_min")
            salary_max = j.get("salary_max")
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
                "salary_min": round(salary_min) if salary_min is not None else None,
                "salary_max": round(salary_max) if salary_max is not None else None,
                # Adzuna's search endpoint doesn't return a per-job
                # currency field -- safe to hardcode since API_URL above
                # is pinned to the "us" country index only (see its
                # docstring on why non-US isn't supported yet).
                "salary_currency": "USD" if (salary_min or salary_max) else "",
                "salary_is_predicted": bool(j.get("salary_is_predicted")),
            })

    return jobs


def fetch_by_keyword_location_pairs(pairs: list[tuple[str, str]]) -> list[dict]:
    """Same shape as fetch_by_keywords, but each (keyword, location) pair
    queries Adzuna's `where` filter directly -- meaningfully boosts the
    odds of finding postings for a narrow, specific location (e.g. a
    profile that only wants "Chicago", no Remote) instead of relying on
    a broad national keyword search to happen to surface enough of
    them. See pipeline_runner._collect_active_location_hints() for how
    the location half of each pair gets chosen.
    """
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        print("[adzuna] skipped (location-paired) -- ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
        return []

    if not pairs:
        print("[adzuna] skipped (location-paired) -- no keyword/location pairs to search")
        return []

    print(f"[adzuna] querying {len(pairs)} location-paired keyword(s): {pairs}")
    all_jobs = []
    for kw, loc in pairs:
        try:
            all_jobs.extend(fetch_jobs_for_keyword(kw, location=loc))
        except Exception as e:
            print(f"[adzuna] unexpected error for pair ({kw!r}, {loc!r}): {e}")
    print(f"[adzuna] done (location-paired) -- {len(all_jobs)} total result(s) across {len(pairs)} pair(s)")
    return all_jobs


def fetch_by_keywords(keywords: list[str]) -> list[dict]:
    """Fetches for several keywords and flattens the results. Per-keyword
    failures (a bad query, a transient 5xx) don't abort the rest -- one
    keyword erroring out shouldn't cost discovery every OTHER keyword's
    results in the same run."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        print("[adzuna] skipped -- ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
        return []

    if not keywords:
        # Distinct from the credentials-missing case above -- keys are
        # fine, but there's nothing to search FOR (e.g. no active
        # search profiles have any titles set yet). Same "returns []
        # either way" ambiguity problem as the credentials check.
        print("[adzuna] skipped -- no keywords to search (no active search profile titles)")
        return []

    print(f"[adzuna] querying {len(keywords)} keyword(s): {keywords}")
    all_jobs = []
    for kw in keywords:
        try:
            all_jobs.extend(fetch_jobs_for_keyword(kw))
        except Exception as e:
            print(f"[adzuna] unexpected error for keyword {kw!r}: {e}")
    print(f"[adzuna] done -- {len(all_jobs)} total result(s) across {len(keywords)} keyword(s)")
    return all_jobs
