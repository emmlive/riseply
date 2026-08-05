"""
Shared rate limiter. Split into its own module so routers can import
`limiter` and apply `@limiter.limit(...)` to individual endpoints without
a circular import with main.py.

Render (and most hosts) sit behind a reverse proxy, so request.client.host
is the proxy's IP, not the real visitor's -- every user would look
identical and rate limiting would either lock out everyone at once or
nobody at all. get_real_client_ip() reads X-Forwarded-For instead, which
Render sets correctly, and falls back to the direct connection IP for
local dev where there's no proxy in front.
"""
from slowapi import Limiter
from starlette.requests import Request


def get_real_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For can be a chain ("client, proxy1, proxy2") --
        # the first entry is the original client.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_real_client_ip)
