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


def _log_email(kind: str, to_addr: str, subject: str, status: str, error: str = "") -> None:
    """Best-effort record of an attempt. Never raises: bookkeeping must not
    turn a sent email into an error, or hide a real one."""
    try:
        from datetime import datetime, timedelta
        import random
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        try:
            db.add(models.EmailLog(kind=kind, to_addr=(to_addr or "")[:200], subject=(subject or "")[:200],
                                   status=status, error=(error or "")[:500]))
            if random.random() < 0.02:  # now and then, drop rows older than 30 days
                db.query(models.EmailLog).filter(
                    models.EmailLog.created_at < datetime.utcnow() - timedelta(days=30)
                ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        print(f"[notifier] couldn't record email log entry: {e}")


def _is_rate_limited(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "ratelimit" in text or "rate limit" in text or "too many requests" in text or "429" in text


def send_email(to_addr: str, subject: str, body: str, attachment_data: bytes | None = None,
               attachment_filename: str = "attachment.docx", kind: str = "other") -> str:
    """Sends through Resend. Returns "sent", or "skipped" when email isn't
    configured on the server. Raises when Resend refuses the message. Every
    attempt is recorded in email_log. A burst of messages can hit Resend's
    per-second limit, so a rate-limit reply is retried a couple of times."""
    if not settings.resend_api_key:
        print(f"[notifier] Resend not configured — skipping email to {to_addr}: {subject}\n{body}\n")
        _log_email(kind, to_addr, subject, "skipped", "RESEND_API_KEY isn't set on the server")
        return "skipped"

    import time
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

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resend.Emails.send(params)
            _log_email(kind, to_addr, subject, "sent")
            return "sent"
        except Exception as e:
            last_error = e
            if attempt < 2 and _is_rate_limited(e):
                time.sleep(1.1 * (attempt + 1))
                continue
            break

    # Prefixed with [Resend] so every caller's error log shows WHERE this failed.
    _log_email(kind, to_addr, subject, "failed", str(last_error))
    raise Exception(f"[Resend] {last_error}") from last_error


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
        kind="new_match",
    )


def notify_submitted(to_addr: str, job: dict):
    send_email(
        to_addr,
        f"Application submitted: {job['title']} @ {job['company']}",
        f"Submitted your application to {job['company']} for {job['title']}.\n{job['url']}",
        kind="submitted",
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
        kind="digest",
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
        kind="welcome",
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
        kind="password_reset",
    )
