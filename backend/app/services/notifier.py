import smtplib
from email.message import EmailMessage

from app.config import settings


def send_email(to_addr: str, subject: str, body: str, attachment_path: str | None = None):
    if not settings.smtp_user or not settings.smtp_pass:
        print(f"[notifier] SMTP not configured — skipping email to {to_addr}: {subject}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_user}>"
    msg["To"] = to_addr
    msg.set_content(body)

    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                data = f.read()
            msg.add_attachment(
                data,
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=attachment_path.split("/")[-1],
            )
        except FileNotFoundError:
            pass

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_pass)
        s.send_message(msg)


def notify_new_match(to_addr: str, job: dict, application_id: int, resume_path: str):
    send_email(
        to_addr,
        f"New job match: {job['title']} @ {job['company']} ({job['match_score']}%)",
        (
            f"{job['title']} at {job['company']}\n"
            f"Matched profile: {job.get('matched_profile', 'n/a')}\n"
            f"Location: {job['location']}\n"
            f"Match score: {job['match_score']}/100 — {job.get('match_reason', '')}\n"
            f"Link: {job['url']}\n\n"
            f"Review and approve/reject it in your dashboard."
        ),
        resume_path,
    )


def notify_submitted(to_addr: str, job: dict):
    send_email(
        to_addr,
        f"Application submitted: {job['title']} @ {job['company']}",
        f"Submitted your application to {job['company']} for {job['title']}.\n{job['url']}",
    )
