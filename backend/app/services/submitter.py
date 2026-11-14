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
import re
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


def _try_fill(page, label: str, value: str) -> bool:
    """Fills the first field with this label, or does nothing at once when the
    page has no such field (no waiting for one that will never appear)."""
    try:
        loc = page.get_by_label(label, exact=False)
        if loc.count() == 0:
            return False
        loc.first.fill(value, timeout=3000)
        return True
    except Exception:
        return False


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

    split_name_found = bool(first_name) and _try_fill(page, "first name", first_name)
    if last_name:
        _try_fill(page, "last name", last_name)

    if not split_name_found and full_name:
        # No separate first/last fields found -- likely a single combined
        # "Name" field (Ashby/Workable pattern). Safe to try broader
        # matches here since we've already confirmed the split fields
        # don't exist, so there's nothing left to collide with.
        for label in ["full name", "name"]:
            if _try_fill(page, label, full_name):
                break

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
        _try_fill(page, label_text, value)

    try:
        files = page.locator('input[type="file"]')
        if resume_path and files.count() > 0:
            files.first.set_input_files(resume_path, timeout=5000)
    except Exception:
        pass


# Visible fields a form marks as required that are still empty. Runs in the page,
# so it sees what a person would. Returns a short label for each.
_UNANSWERED_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const label = (el) => {
    const id = el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    const t = (id && id.innerText) || el.getAttribute('aria-label') || el.placeholder
      || (el.closest('label') && el.closest('label').innerText) || el.name || el.type || 'a required question';
    return t.replace(/\s+/g, ' ').replace(/[*]/g, '').trim().slice(0, 80);
  };
  const out = [];
  const seenGroups = new Set();
  document.querySelectorAll('input, select, textarea').forEach((el) => {
    const required = el.required || el.getAttribute('aria-required') === 'true';
    if (!required || el.disabled || el.type === 'hidden') return;
    if (el.type === 'file') { if (!el.files || el.files.length === 0) out.push(label(el)); return; }
    if (!vis(el)) return;
    if (el.type === 'radio') {
      if (seenGroups.has(el.name)) return; seenGroups.add(el.name);
      if (!document.querySelector('input[type=radio][name="' + CSS.escape(el.name) + '"]:checked')) out.push(label(el));
      return;
    }
    if (el.type === 'checkbox') { if (!el.checked) out.push(label(el)); return; }
    if (!String(el.value || '').trim()) out.push(label(el));
  });
  return out;
}
"""

_SUCCESS = re.compile(
    r"thank you for (applying|your application|your interest)|application (has been |was )?(successfully )?(submitted|received|sent)"
    r"|we(\'ve| have) received your application|successfully (applied|submitted)|you(\'ve| have) applied", re.I)
_SUCCESS_URL = re.compile(r"confirmation|thank|submitted|applied|success", re.I)
_ERROR_TEXT = re.compile(r"this field is required|is required|please (fill|enter|select|complete|correct)|can.?t be blank|invalid", re.I)


def unanswered_required(page) -> list[str]:
    try:
        found = page.evaluate(_UNANSWERED_JS)
    except Exception:
        return ["the form (couldn't be checked)"]
    seen, out = set(), []
    for x in found or []:
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def confirm_submitted(page, url_before: str, wait_ms: int = 9000) -> tuple[str, str]:
    """After clicking Submit: ("ok", ...) only when the site itself says the
    application went through. ("errors", ...) when the form is showing problems,
    ("unknown", ...) when neither can be seen. Never guesses success."""
    waited = 0
    while waited <= wait_ms:
        try:
            body = page.inner_text("body", timeout=2000)
        except Exception:
            body = ""
        if _SUCCESS.search(body or "") or (page.url != url_before and _SUCCESS_URL.search(page.url)):
            return "ok", "Confirmed by the site."
        bad = unanswered_required(page)
        invalid = False
        try:
            invalid = page.locator('[aria-invalid="true"]').count() > 0
        except Exception:
            pass
        if bad or invalid or (_ERROR_TEXT.search(body or "") and page.url == url_before and waited >= 3000):
            return "errors", ("The site asked for: " + ", ".join(bad[:4])) if bad else "The site showed a form error."
        page.wait_for_timeout(500)
        waited += 500
    return "unknown", "Couldn't confirm the site accepted it."


def submit_application(job_url: str, resume_path: str, candidate: dict, actually_submit: bool) -> dict:
    """Returns {"status": "submitted" | "needs_manual_review" | "failed",
    "detail": str}. Never raises -- every failure mode is caught and
    reported, since this may run unattended.

    "submitted" is only returned when the site itself confirms it. It stops
    for a person, without clicking Submit, when the resume didn't attach or any
    required question is still unanswered, because guessing at legal, work
    authorization or demographic questions is never acceptable."""
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
                        btn = page.get_by_role("button", name=label)
                        if btn.count() > 0:
                            btn.first.click(timeout=3000)
                            break
                    except Exception:
                        continue

                _fill_common_fields(page, candidate, resume_path)

                if page.locator("iframe[src*='captcha'], iframe[src*='recaptcha']").count() > 0:
                    browser.close()
                    return {"status": "needs_manual_review", "detail": "CAPTCHA detected — needs a human to finish this one."}

                if resume_path:
                    try:
                        files = page.locator('input[type="file"]')
                        attached = files.first.evaluate("el => el.files && el.files.length") if files.count() > 0 else 0
                    except Exception:
                        attached = 0
                    if not attached:
                        browser.close()
                        return {"status": "needs_manual_review", "detail": "The resume didn't attach — needs a human to finish this one."}

                missing = unanswered_required(page)
                if missing:
                    browser.close()
                    return {"status": "needs_manual_review",
                            "detail": "Needs your answer to: " + ", ".join(missing[:5]) + (" and more." if len(missing) > 5 else ".")}

                if not actually_submit:
                    browser.close()
                    return {"status": "needs_manual_review", "detail": "Form filled — review and submit manually (auto-submit is off)."}

                url_before = page.url
                clicked = False
                for label in ["Submit Application", "Submit", "Send Application"]:
                    try:
                        btn = page.get_by_role("button", name=label)
                        if btn.count() > 0:
                            btn.first.click(timeout=3000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    browser.close()
                    return {"status": "needs_manual_review", "detail": "Couldn't find a submit button — needs manual completion."}

                verdict, detail = confirm_submitted(page, url_before)
                browser.close()
                if verdict == "ok":
                    return {"status": "submitted", "detail": "ok"}
                if verdict == "errors":
                    return {"status": "needs_manual_review", "detail": f"Submit was clicked but the form wasn't accepted. {detail}"}
                return {"status": "needs_manual_review",
                        "detail": "Submit was clicked, but the site never confirmed it. Check the job's page before applying again."}

            except Exception as e:
                browser.close()
                return {"status": "failed", "detail": f"Automation error: {e}"}
    except Exception as e:
        return {"status": "failed", "detail": f"Couldn't start the browser: {e}"}
