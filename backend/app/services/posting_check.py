"""Is this job posting still open?

Job links come from third-party feeds, so we only ever do a plain GET on
public http(s) addresses (private, loopback and link-local addresses are
refused, including after redirects) and read a small slice of the page.

check_posting() answers three ways, on purpose:
  True   the page loaded and shows no sign the job is closed
  False  the posting is clearly closed (404/410, the Greenhouse
         "?error=true" redirect, or the page says so in plain words)
  None   we couldn't tell (blocked by the site, timeout, no link).
         Callers must treat None as "keep it" -- many job boards refuse
         non-browser requests, and hiding a good job because a site
         blocked us would be worse than showing one that has closed.
"""
import ipaddress
import re
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT_SECONDS = 6
MAX_REDIRECTS = 4
MAX_BYTES = 250_000

CLOSED_PHRASES = (
    "no longer accepting applications",
    "no longer accepting applicants",
    "this job is no longer available",
    "this job has expired",
    "this job posting has expired",
    "this posting has expired",
    "this position has been filled",
    "this position is no longer available",
    "this job has been filled",
    "job is closed",
    "position is closed",
    "this role is no longer available",
    "sorry, this job is no longer",
    "the job you are looking for is no longer open",
    "this job is no longer open",
    "this position is no longer open",
    "this posting is no longer active",
    "this opportunity is no longer available",
    "position has been closed",
    "this job has been closed",
    "this role has been filled",
    "no longer available for applications",
    "applications are closed",
    "job not found",
)

# schema.org JobPosting markup, which most job pages carry for search
# engines, says when the posting stops being valid.
_VALID_THROUGH = re.compile(r'"validThrough"\s*:\s*"([^"]{8,40})"', re.I)


def expired_by_markup(text: str, now: datetime | None = None) -> bool:
    """True when the page's own JobPosting markup says it expired in the
    past. A date we can't read counts as "not expired"."""
    now = now or datetime.utcnow()
    for raw in _VALID_THROUGH.findall(text or ""):
        raw = raw.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        elif len(raw) <= 10:
            parsed += timedelta(days=1)  # a bare date is valid through the end of that day
        if parsed < now:
            return True
    return False


def _is_public_host(hostname: str) -> bool:
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return bool(infos)


def page_says_closed(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(phrase in lowered for phrase in CLOSED_PHRASES)


def check_posting(url: str):
    """True = open, False = closed, None = couldn't tell. Never raises."""
    try:
        current = (url or "").strip()
        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not _is_public_host(parsed.hostname or ""):
                return None
            if "error=true" in (parsed.query or "").lower():
                return False  # Greenhouse sends closed jobs back to the board with this flag

            resp = requests.get(current, headers=HEADERS, timeout=TIMEOUT_SECONDS,
                                allow_redirects=False, stream=True)
            try:
                if resp.status_code in (404, 410):
                    return False
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                if resp.status_code >= 400:
                    return None  # blocked / rate limited / server trouble: unknown
                body = b""
                for chunk in resp.iter_content(chunk_size=16_384):
                    body += chunk
                    if len(body) >= MAX_BYTES:
                        break
                text = body.decode(resp.encoding or "utf-8", errors="ignore")
                return False if (page_says_closed(text) or expired_by_markup(text)) else True
            finally:
                resp.close()
        return None  # too many redirects
    except Exception:
        return None
