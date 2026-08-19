"""
Pulls postings from RemoteOK's public JSON API (https://remoteok.com/api) --
free, no authentication required, no key to register for. Genuinely
general-purpose: despite the name recognition being programming-heavy,
RemoteOK lists roles across many functions (Developer, Designer,
Copywriter, Customer Support, Sales, Marketing, Project Manager, and
more), so this is a broad additional job bank rather than another
industry-specific source.

Legal note: RemoteOK's own terms (stated on their API help page and
referenced across their public API documentation) require attributing
RemoteOK as the source and linking DIRECTLY to the job listing on
RemoteOK, no redirects. Every job dict below uses the listing's own
`url` field from the API response as its `url` -- that link IS the
direct RemoteOK listing page, satisfying both requirements.

IMPORTANT CAVEAT: this module was written without being able to do a
live fetch against the real endpoint from the build environment (the
domain wasn't reachable from that sandbox). The field names below
(company, position, tags, location, description, url, salary_min,
salary_max) are RemoteOK's long-standing, widely-referenced public API
shape -- but this has NOT been verified against a live response the
way adzuna.py was. Every field access below uses .get() with a safe
default specifically because of that uncertainty, and the diagnostic
prints are deliberately verbose (raw response shape on the very first
run) so any mismatch between what's assumed here and what the API
actually returns is immediately visible in Render's logs rather than
silently producing zero or malformed results.
"""
import requests

API_URL = "https://remoteok.com/api"

# RemoteOK blocks generic/bot-looking User-Agents on this endpoint (a
# documented quirk of their API) -- a realistic browser UA avoids that.
# Same approach already used in rss_boards.py for the same reason.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_jobs() -> list[dict]:
    """RemoteOK's API has no keyword/pagination parameters -- it returns
    its full current listing set in one call, so there's nothing to
    loop over here the way adzuna.py loops over keywords. Filtering to
    what's actually relevant happens downstream, same as every other
    bulk source (greenhouse.py, rss_boards.py) -- this just supplies
    the raw pool.
    """
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[remoteok] fetch failed: {e}")
        return []
    except ValueError as e:  # response wasn't valid JSON
        print(f"[remoteok] response wasn't valid JSON: {e}")
        return []

    if not isinstance(data, list):
        print(f"[remoteok] unexpected response shape (expected a list, got {type(data).__name__}) -- skipping")
        return []

    # The documented RemoteOK API shape has a legal/metadata notice as
    # the FIRST array element (not a job posting) -- distinguishable
    # from real job entries by having no "id" field. Skipping it
    # defensively by checking for "id" rather than assuming it's always
    # exactly one leading element, in case the API's exact shape has
    # drifted since this was written (see the module docstring).
    jobs_raw = [entry for entry in data if isinstance(entry, dict) and entry.get("id")]
    print(f"[remoteok] fetched {len(data)} raw entries, {len(jobs_raw)} look like real job postings")

    if data and not jobs_raw:
        # Every entry got filtered out -- either the whole response was
        # just the legal notice (API hiccup) or the field names this
        # code assumes (see docstring) no longer match reality. Log a
        # sample of the first entry's actual keys so a mismatch is
        # diagnosable from Render's logs without needing to reproduce
        # it locally.
        sample_keys = list(data[0].keys()) if isinstance(data[0], dict) else "not a dict"
        print(f"[remoteok] WARNING: zero postings survived filtering -- first raw entry's keys: {sample_keys}")

    jobs = []
    for entry in jobs_raw:
        salary_min = entry.get("salary_min")
        salary_max = entry.get("salary_max")
        tags = entry.get("tags") or []
        jobs.append({
            "source": "remoteok",
            "external_id": str(entry.get("id", "")),
            "company": entry.get("company", ""),
            "title": entry.get("position", "") or entry.get("title", ""),
            # RemoteOK postings are all remote by definition -- when the
            # API doesn't supply a more specific location string,
            # falling back to "Remote" rather than "" so this source's
            # jobs reliably pass the Remote-synonym location filter
            # (see matcher._location_matches) instead of only doing so
            # when the field happens to be populated.
            "location": entry.get("location") or "Remote",
            "url": entry.get("url", ""),
            "description": entry.get("description", "") + (
                f"\n\nTags: {', '.join(tags)}" if tags else ""
            ),
            "salary_min": int(salary_min) if isinstance(salary_min, (int, float)) else None,
            "salary_max": int(salary_max) if isinstance(salary_max, (int, float)) else None,
            "salary_currency": "USD" if (salary_min or salary_max) else "",
            "salary_is_predicted": False,  # RemoteOK salaries, when present, are employer-stated
        })

    return jobs
