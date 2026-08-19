"""
Pulls postings from Arbeitnow's public job board API
(https://www.arbeitnow.com/api/job-board-api) -- free, no authentication
required, no key to register for. Confirmed directly from Arbeitnow's
own blog (arbeitnow.com/blog/job-board-api, updated August 2026): the
endpoint aggregates real postings from several ATS platforms
(Greenhouse, SmartRecruiters, Join.com, Team Tailor, Recruitee, Comeet)
into one consistent format, and includes a `remote` boolean field.
Genuinely general-purpose across industries, not a single-industry
source -- primarily Europe-based postings (the board itself is
Berlin-built), but that's complementary rather than redundant with the
US-centric sources already in this codebase, and its `remote` field
means non-EU-specific remote roles are exactly the kind of listing the
existing location matcher (see matcher._location_matches's remote-
synonym handling) already knows how to surface for a Remote-seeking
profile regardless of what country the employer is in.

IMPORTANT CAVEAT, same situation as remoteok.py: this module was
written without being able to do a live fetch against the real
endpoint from the build environment (the domain wasn't reachable from
that sandbox), and the official Postman documentation page is
JavaScript-rendered, so its exact field-by-field schema couldn't be
confirmed either. The field names below (title, company_name,
location, description, url, remote, tags, created_at) reflect
Arbeitnow's own blog post plus consistent references across multiple
independent third-party integrations (Apify scrapers, public API
directories) describing the same shape -- but this has NOT been
verified against a live response the way adzuna.py's shape was. Every
field access below uses .get() with a safe default specifically
because of that uncertainty, and the diagnostic logging is deliberately
verbose (the actual keys of the first entry, on any parsing failure)
so a mismatch between what's assumed here and what the API actually
returns is immediately visible in Render's logs on the very first real
run, rather than silently producing zero or malformed results -- same
philosophy as remoteok.py.
"""
import requests

API_URL = "https://www.arbeitnow.com/api/job-board-api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_jobs() -> list[dict]:
    """Arbeitnow's documented API has no keyword-search parameter --
    like remoteok.py, this returns its current listing set in one call
    (a `visa_sponsorship=true/false` filter exists per the official
    blog, deliberately not used here since filtering to sponsorship-
    only would narrow the pool rather than broaden it, which is the
    whole point of adding this source). Downstream relevance filtering
    happens the same way it does for every other bulk source
    (greenhouse.py, rss_boards.py, remoteok.py) -- this just supplies
    the raw pool.
    """
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[arbeitnow] fetch failed: {e}")
        return []
    except ValueError as e:  # response wasn't valid JSON
        print(f"[arbeitnow] response wasn't valid JSON: {e}")
        return []

    # Documented shape is {"data": [...]} -- but given the schema
    # couldn't be verified live (see module docstring), also tolerate
    # a bare top-level list, in case that assumption is wrong.
    if isinstance(data, dict):
        jobs_raw = data.get("data", [])
    elif isinstance(data, list):
        jobs_raw = data
    else:
        print(f"[arbeitnow] unexpected response shape (expected a dict with 'data' or a list, got {type(data).__name__}) -- skipping")
        return []

    if not isinstance(jobs_raw, list):
        print(f"[arbeitnow] 'data' field wasn't a list (got {type(jobs_raw).__name__}) -- skipping")
        return []

    print(f"[arbeitnow] fetched {len(jobs_raw)} raw entries")

    if jobs_raw and not isinstance(jobs_raw[0], dict):
        sample = jobs_raw[0]
        print(f"[arbeitnow] WARNING: entries aren't dicts as expected -- first entry: {sample!r}")
        return []

    jobs = []
    skipped_no_id = 0
    for entry in jobs_raw:
        # slug is Arbeitnow's stable per-posting identifier (per its
        # use in the board's own posting URLs) -- entries missing one
        # aren't usable as a dedup key downstream, so they're skipped
        # rather than risking a duplicate/unstable external_id.
        slug = entry.get("slug")
        if not slug:
            skipped_no_id += 1
            continue

        tags = entry.get("tags") or []
        job_types = entry.get("job_types") or []
        is_remote = bool(entry.get("remote"))
        location = entry.get("location") or ""
        if not location and is_remote:
            # Same reasoning as remoteok.py's identical fallback -- an
            # explicitly remote posting with no location string should
            # still pass the Remote-synonym location filter (see
            # matcher._location_matches) rather than only doing so when
            # the field happens to be populated.
            location = "Remote"

        description = entry.get("description", "")
        extra_context = []
        if tags:
            extra_context.append(f"Tags: {', '.join(tags)}")
        if job_types:
            extra_context.append(f"Job type: {', '.join(job_types)}")
        if extra_context:
            description = f"{description}\n\n{chr(10).join(extra_context)}"

        jobs.append({
            "source": "arbeitnow",
            "external_id": str(slug),
            "company": entry.get("company_name", ""),
            "title": entry.get("title", ""),
            "location": location,
            "url": entry.get("url", ""),
            "description": description,
            # Arbeitnow's documented fields don't include a structured
            # salary range (per the Apify listing's own caveat: "does
            # not consistently publish structured salary ranges") --
            # left as None/"" rather than guessing at a field name that
            # may not exist.
            "salary_min": None, "salary_max": None,
            "salary_currency": "", "salary_is_predicted": False,
        })

    if skipped_no_id:
        print(f"[arbeitnow] skipped {skipped_no_id} entr{'y' if skipped_no_id == 1 else 'ies'} with no slug (unusable as a dedup key)")

    if jobs_raw and not jobs:
        sample_keys = list(jobs_raw[0].keys()) if isinstance(jobs_raw[0], dict) else "not a dict"
        print(f"[arbeitnow] WARNING: zero postings survived filtering -- first raw entry's keys: {sample_keys}")

    return jobs
