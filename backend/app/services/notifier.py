from app.config import settings


def _format_salary(job: dict) -> str:
    """Shared by every email template that shows a job. Returns "" when
    there's nothing to show (most Greenhouse/Lever/RSS postings, and
    some Adzuna ones -- not every posting states or predicts a salary)
    so callers can just conditionally append a line rather than every
    template re-implementing this same "do we actually have both
    numbers" check.
    """
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if not lo and not hi:
        return ""
    currency = job.get("salary_currency") or "USD"
    symbol = "$" if currency == "USD" else f"{currency} "
    if lo and hi and lo != hi:
        range_str = f"{symbol}{lo:,.0f}–{symbol}{hi:,.0f}"
    else:
        range_str = f"{symbol}{(hi or lo):,.0f}"
    return f"{range_str} (estimated)" if job.get("salary_is_predicted") else range_str


def send_email(to_addr: str, subject: str, body: str, attachment_data: bytes | None = None, attachment_filename: str = "attachment.docx"):
    if not settings.resend_api_key:
        print(f"[notifier] Resend not configured — skipping email to {to_addr}: {subject}\n{body}\n")
        return

    import resend
    resend.api_key = settings.resend_api_key

    params: dict = {
        "from": f"{settings.resend_from_name} <{settings.resend_from_email}>",
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    if attachment_data:
        # Python SDK specifically wants content as a list of ints (raw
        # bytes), NOT a base64 string -- that's the JS SDK's format.
        # Getting this backwards fails silently-ish (a confusing API
        # error), so it's worth this comment existing.
        params["attachments"] = [{"content": list(attachment_data), "filename": attachment_filename}]

    try:
        resend.Emails.send(params)
    except Exception as e:
        # Prefixed with [Resend] for the same reason the old SMTP path
        # prefixed [host:port] -- every caller's error log should show
        # WHERE this failed without needing to go dig through code.
        raise Exception(f"[Resend] {e}") from e


def notify_new_match(to_addr: str, job: dict, application_id: int, resume_filename: str = "", resume_data: bytes | None = None):
    salary = _format_salary(job)
    send_email(
        to_addr,
        f"New job match: {job['title']} @ {job['company']} ({job['match_score']}%)",
        (
            f"{job['title']} at {job['company']}\n"
            f"Matched profile: {job.get('matched_profile', 'n/a')}\n"
            f"Location: {job['location']}\n"
            + (f"Salary: {salary}\n" if salary else "")
            + f"Match score: {job['match_score']}/100 — {job.get('match_reason', '')}\n"
            f"Link: {job['url']}\n\n"
            f"Review and approve/reject it in your dashboard."
        ),
        resume_data,
        resume_filename or "resume.docx",
    )


def notify_submitted(to_addr: str, job: dict):
    send_email(
        to_addr,
        f"Application submitted: {job['title']} @ {job['company']}",
        f"Submitted your application to {job['company']} for {job['title']}.\n{job['url']}",
    )


def notify_digest(to_addr: str, matches: list[dict]):
    """One email summarizing every match since the last digest, for
    users on notification_preference='daily_digest'. matches is a list
    of {title, company, location, match_score, match_reason, url}."""
    if not matches:
        return
    matches_sorted = sorted(matches, key=lambda m: m["match_score"], reverse=True)
    lines = []
    for m in matches_sorted:
        salary = _format_salary(m)
        salary_part = f" — {salary}" if salary else ""
        lines.append(f"- {m['title']} @ {m['company']} ({m['match_score']}%) — {m['location']}{salary_part}\n  {m['url']}")
    count = len(matches)
    send_email(
        to_addr,
        f"Your Riseply digest: {count} new match{'es' if count != 1 else ''}",
        (
            f"{count} new match{'es' if count != 1 else ''} since your last digest:\n\n"
            + "\n\n".join(lines)
            + "\n\nReview and approve/reject them in your dashboard."
        ),
    )


def notify_welcome(to_addr: str, full_name: str = ""):
    name_part = f", {full_name}" if full_name else ""
    send_email(
        to_addr,
        "Welcome to Riseply",
        (
            f"Hey{name_part},\n\n"
            f"Welcome to Riseply. Here's how to get started:\n\n"
            f"1. Add your resume — Resume tab in your dashboard\n"
            f"2. Set up a search profile — tell Riseply what roles/locations you're targeting\n"
            f"3. Hit \"Find new matches\" on your Overview page\n\n"
            f"Everything gets queued for your review — nothing gets submitted without your OK.\n\n"
            f"Questions? Just reply to this email or use the Support tab in your dashboard.\n\n"
            f"— Riseply"
        ),
    )


def notify_password_reset(to_addr: str, reset_url: str, expire_minutes: int):
    send_email(
        to_addr,
        "Reset your Riseply password",
        (
            f"Someone (hopefully you) requested a password reset for this Riseply account.\n\n"
            f"Reset your password here — this link expires in {expire_minutes} minutes and "
            f"can only be used once:\n{reset_url}\n\n"
            f"If you didn't request this, you can safely ignore this email — your password "
            f"won't change unless you click the link above and set a new one."
        ),
    )
