"""
Pulls postings from USAJobs' official Search API
(https://data.usajobs.gov/api/search) -- the US federal government's
own job board. Free, self-serve registration at
https://developer.usajobs.gov/apirequest/. Genuinely broad across
industries WITHIN federal hiring (IT, healthcare, law enforcement,
science, administration, and more) -- keyword-driven like adzuna.py,
not a fixed company/agency list, so it automatically follows whatever
titles are actually in people's active search profiles, the same
scalable, industry-agnostic pattern already established for Adzuna.

Confirmed directly against USAJobs' own official documentation
(developer.usajobs.gov/guides/authentication,
developer.usajobs.gov/tutorials/search-jobs,
developer.usajobs.gov/api-reference/get-api-Search) as of this
writing -- unlike remoteok.py/arbeitnow.py, this was NOT built
defensively against an unverified schema. The endpoint, required
headers, query parameters, and response shape below are all taken
directly from USAJobs' own docs, not inferred from third-party
sources.

AUTHENTICATION IS UNUSUAL: three headers are required on every
request -- Host, User-Agent, and Authorization-Key. The User-Agent
header must be the email address registered when the key was issued,
NOT a browser identification string -- USAJobs' own docs call this
convention out specifically because it inverts the header's usual
meaning and is the most common cause of authentication errors with an
otherwise-valid key.
"""
import requests

from app.config import settings

API_URL = "https://data.usajobs.gov/api/search"


def fetch_jobs_for_keyword(keyword: str, location: str = "") -> list[dict]:
    """One keyword, one page (up to settings.usajobs_results_per_page
    results). Returns normalized job dicts in the same shape
    run_discovery() expects from every other source.
    """
    if not settings.usajobs_api_key or not settings.usajobs_email:
        print("[usajobs] skipped -- USAJOBS_API_KEY/USAJOBS_EMAIL not set")
        return []

    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": settings.usajobs_email,
        "Authorization-Key": settings.usajobs_api_key,
    }
    params = {
        "Keyword": keyword,
        "ResultsPerPage": settings.usajobs_results_per_page,
    }
    if location:
        params["LocationName"] = location

    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        # USAJobs auth errors (wrong key, or a browser-style User-Agent
        # instead of the registered email -- the exact mistake its own
        # docs warn about) come back as an HTTP error here, and the
        # response body is where USAJobs actually explains why --
        # surfacing it is the difference between "it's broken" and
        # "the User-Agent header needs to be an email address."
        body = getattr(e, "response", None)
        body_text = body.text[:300] if body is not None else "(no response body)"
        print(f"[usajobs] failed for keyword {keyword!r}: {e} -- body: {body_text}")
        return []
    except ValueError as e:
        print(f"[usajobs] response wasn't valid JSON for keyword {keyword!r}: {e}")
        return []

    search_result = data.get("SearchResult", {})
    items = search_result.get("SearchResultItems", [])
    print(f"[usajobs] keyword {keyword!r}: {len(items)} results")

    jobs = []
    for item in items:
        # MatchedObjectId and MatchedObjectDescriptor are both directly
        # confirmed field names from USAJobs' own API reference example
        # response -- not a guess.
        object_id = item.get("MatchedObjectId")
        descriptor = item.get("MatchedObjectDescriptor") or {}
        if not object_id or not descriptor:
            continue

        apply_uris = descriptor.get("ApplyURI") or []
        url = apply_uris[0] if apply_uris else descriptor.get("PositionURI", "")

        # OrganizationName (the specific sub-agency, e.g. "Space and
        # Naval Warfare Systems Command") is confirmed from the same
        # example response; DepartmentName (the parent department,
        # e.g. "Department of the Navy") as a fallback for the rarer
        # case OrganizationName is blank.
        company = descriptor.get("OrganizationName") or descriptor.get("DepartmentName", "")

        # UserArea.Details.JobSummary and PositionRemuneration are
        # documented elsewhere in USAJobs' schema but weren't in the
        # specific example response confirmed for this module -- kept
        # defensive (.get() with fallbacks) for exactly these two
        # fields, unlike the rest of this function.
        user_area = descriptor.get("UserArea") or {}
        details = user_area.get("Details") or {}
        description = details.get("JobSummary") or descriptor.get("QualificationSummary", "")

        salary_min = None
        salary_max = None
        remuneration = descriptor.get("PositionRemuneration") or []
        if remuneration:
            first = remuneration[0] or {}
            try:
                if first.get("MinimumRange") not in (None, ""):
                    salary_min = round(float(first["MinimumRange"]))
                if first.get("MaximumRange") not in (None, ""):
                    salary_max = round(float(first["MaximumRange"]))
            except (TypeError, ValueError):
                pass  # malformed salary field -- leave as None rather than guess

        jobs.append({
            "source": "usajobs",
            "external_id": str(object_id),
            "company": company,
            "title": descriptor.get("PositionTitle", ""),
            "location": descriptor.get("PositionLocationDisplay", ""),
            "url": url,
            "description": description,
            "salary_min": salary_min, "salary_max": salary_max,
            # Federal pay is scale-based and always explicitly stated
            # on the announcement, never modeled/estimated -- unlike
            # Adzuna's salary_is_predicted, this is never True here.
            "salary_currency": "USD" if (salary_min or salary_max) else "",
            "salary_is_predicted": False,
        })

    return jobs


def fetch_by_keywords(keywords: list[str]) -> list[dict]:
    """Fetches for several keywords and flattens the results. Per-
    keyword failures don't abort the rest -- one keyword erroring out
    shouldn't cost every OTHER keyword's results in the same run.
    """
    if not settings.usajobs_api_key or not settings.usajobs_email:
        print("[usajobs] skipped -- USAJOBS_API_KEY/USAJOBS_EMAIL not set")
        return []

    if not keywords:
        print("[usajobs] skipped -- no keywords to search (no active search profile titles)")
        return []

    print(f"[usajobs] querying {len(keywords)} keyword(s): {keywords}")
    all_jobs = []
    for kw in keywords:
        try:
            all_jobs.extend(fetch_jobs_for_keyword(kw))
        except Exception as e:
            print(f"[usajobs] unexpected error for keyword {kw!r}: {e}")
    print(f"[usajobs] done -- {len(all_jobs)} total result(s) across {len(keywords)} keyword(s)")
    return all_jobs
