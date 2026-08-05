"""
Auto-submit: fills and (optionally) submits a job application form via
Playwright, restricted to an explicit allowlist of ATS domains.

This is deliberately conservative:
- ALLOWLIST, not a blocklist. LinkedIn, Indeed, and anything else not on
  the list are blocked by default, not just discouraged -- and even
  though it should never match those domains via the allowlist check
  alone, is_supported_ats() also explicitly hard-blocks a short list of
  known consumer job boards as defense in depth.
- Only ever called on an application the user has already approved
  (enforced by the router, not this module) -- this never runs against
  a job the user hasn't reviewed.
- Global settings.auto_submit_enabled kill-switch, checked by the
  router before this module is even invoked.
- Defaults to stopping one step before the final submit click even when
  everything else succeeds, controlled by a separate parameter -- so
  "fill the form" and "actually send it" are two distinct decisions.
"""
from urllib.parse import urlparse

from app.config import settings

# Defense in depth: these are hard-blocked even if a future config change
# accidentally added them to the allowlist. Automating submissions on
# these platforms risks violating their Terms of Service around bot
# activity, and that's not something this app will do regardless of any
# per-user or per-admin setting.
HARD_BLOCKED_DOMAINS = {
    "linkedin.com", "www.linkedin.com",
    "indeed.com", "www.indeed.com",
}


def is_supported_ats(url: str) -> tuple[bool, str]:
    """Returns (allowed, reason). Allowed only if the domain is in the
    explicit allowlist AND not in the hard-blocked set."""
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return False, "Couldn't parse that URL."

    if domain in HARD_BLOCKED_DOMAINS:
        return False, f"{domain} is explicitly blocked — automated submission there isn't supported."

    if domain not in settings.auto_submit_allowed_domains_list:
        return False, f"{domain} isn't a supported ATS for auto-submit yet — only Greenhouse and Lever are."

    return True, "ok"


def _fill_common_fields(page, candidate: dict, resume_path: str):
    """Best-effort generic filler for common ATS field patterns
    (Greenhouse, Lever, Ashby, Workable). Real forms vary; this handles
    the common cases and leaves anything it can't confidently fill blank
    rather than guessing wrong.

    Two name conventions exist across these platforms: Greenhouse/Lever
    typically split first/last name into separate fields, while Ashby/
    Workable commonly use a single combined "Name" field. Filling both
    conventions with one static field map caused a real bug once already
    (a bare "name" search matched both "First Name" and "Last Name" and
    overwrote the first-name value) -- so this checks which pattern is
    actually present before deciding what to fill, rather than trying
    every possible label unconditionally.
    """
    first_name = candidate.get("first_name", "")
    last_name = candidate.get("last_name", "")
    full_name = candidate.get("full_name", "")

    split_name_found = False
    if first_name:
        try:
            page.get_by_label("first name", exact=False).first.fill(first_name, timeout=1500)
            split_name_found = True
        except Exception:
            pass
    if last_name:
        try:
            page.get_by_label("last name", exact=False).first.fill(last_name, timeout=1500)
        except Exception:
            pass

    if not split_name_found and full_name:
        # No separate first/last fields found -- likely a single combined
        # "Name" field (Ashby/Workable pattern). Safe to try broader
        # matches here since we've already confirmed the split fields
        # don't exist, so there's nothing left to collide with.
        for label in ["full name", "name"]:
            try:
                page.get_by_label(label, exact=False).first.fill(full_name, timeout=1500)
                break
            except Exception:
                continue

    field_map = {
        "email": candidate.get("email", ""),
        "phone": candidate.get("phone", ""),
        "location": candidate.get("location", ""),
        "linkedin": candidate.get("linkedin_url", ""),
        "website": candidate.get("portfolio_url", ""),
    }

    for label_text, value in field_map.items():
        if not value:
            continue
        try:
            page.get_by_label(label_text, exact=False).first.fill(value, timeout=1500)
        except Exception:
            continue

    try:
        file_input = page.locator('input[type="file"]').first
        if resume_path:
            file_input.set_input_files(resume_path, timeout=3000)
    except Exception:
        pass


def submit_application(job_url: str, resume_path: str, candidate: dict, actually_submit: bool) -> dict:
    """Returns {"status": "submitted" | "needs_manual_review" | "failed",
    "detail": str}. Never raises -- every failure mode is caught and
    reported, since this may run unattended."""
    allowed, reason = is_supported_ats(job_url)
    if not allowed:
        return {"status": "failed", "detail": reason}

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(job_url, timeout=30000)

                for label in ["Apply", "Apply Now", "Apply for this job"]:
                    try:
                        page.get_by_role("button", name=label).first.click(timeout=2000)
                        break
                    except Exception:
                        continue

                _fill_common_fields(page, candidate, resume_path)

                if page.locator("iframe[src*='captcha'], iframe[src*='recaptcha']").count() > 0:
                    browser.close()
                    return {"status": "needs_manual_review", "detail": "CAPTCHA detected — needs a human to finish this one."}

                if not actually_submit:
                    browser.close()
                    return {"status": "needs_manual_review", "detail": "Form filled — review and submit manually (auto-submit is off)."}

                for label in ["Submit Application", "Submit", "Send Application"]:
                    try:
                        page.get_by_role("button", name=label).first.click(timeout=3000)
                        browser.close()
                        return {"status": "submitted", "detail": "ok"}
                    except Exception:
                        continue

                browser.close()
                return {"status": "needs_manual_review", "detail": "Couldn't find a submit button — needs manual completion."}

            except Exception as e:
                browser.close()
                return {"status": "failed", "detail": f"Automation error: {e}"}
    except Exception as e:
        return {"status": "failed", "detail": f"Couldn't start the browser: {e}"}
