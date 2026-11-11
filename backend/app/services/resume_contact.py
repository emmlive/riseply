"""The contact details printed at the top of a resume. When Riseply fills an
application or creates an account on an employer's site, it uses the email and
phone on the resume, because that is what the recruiter will see and use."""
import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]*)?\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}(?!\d)")
HEADER_CHARS = 1500


def extract(text: str) -> dict:
    head = (text or "")[:HEADER_CHARS]
    email = _EMAIL.search(head)
    phone = _PHONE.search(head)
    return {"email": email.group(0) if email else "", "phone": phone.group(0).strip() if phone else ""}
