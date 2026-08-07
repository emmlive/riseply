"""
SMS via Twilio. Same pattern as notifier.send_email()'s SMTP handling:
until all three Twilio settings are configured, send_sms() prints and
skips rather than failing -- there's no "unauthenticated SMS blast"
default, same reasoning as every other kill-switched integration in
this codebase (Stripe, CRON_SECRET, admin bootstrap).

Compliance note, not just a code comment: US law (TCPA) requires
explicit opt-in consent before sending someone marketing/notification
SMS, and unregistered business SMS traffic gets filtered or blocked by
carriers (A2P 10DLC registration). Both of those are account/legal
setup on Twilio's side, not something this module can enforce by
itself -- but see User.sms_consent, which gates whether this ever gets
called for a given user in the first place.
"""
from app.config import settings

MAX_SMS_LENGTH = 1500  # ~10 segments -- Twilio splits/concatenates automatically, but stay well short of it


def send_sms(to_number: str, body: str):
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
        print(f"[sms] Twilio not configured — skipping SMS to {to_number}: {body}")
        return
    if not to_number:
        print(f"[sms] No phone number on file — skipping SMS: {body}")
        return

    from twilio.rest import Client

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(
        body=body[:MAX_SMS_LENGTH],
        from_=settings.twilio_from_number,
        to=to_number,
    )


def notify_new_match_sms(to_number: str, job: dict):
    send_sms(
        to_number,
        f"Riseply: new match — {job['title']} @ {job['company']} ({job['match_score']}%). "
        f"Review it in your dashboard. Reply STOP to unsubscribe.",
    )


def notify_digest_sms(to_number: str, match_count: int):
    # Deliberately short -- SMS isn't the place for a full listing the
    # way the email digest is; this just prompts a dashboard visit.
    send_sms(
        to_number,
        f"Riseply: {match_count} new match{'es' if match_count != 1 else ''} today. "
        f"Check your dashboard for details. Reply STOP to unsubscribe.",
    )
