"""
Rate-limit key derivation + the shared `Limiter` instance.

slowapi's default `get_remote_address` reads `request.client.host`, which
behind Cloud Run / Vercel / any LB is always the LB's IP — so every
client in the world shares a single rate-limit bucket. Useless.

When `RATE_LIMIT_TRUST_FORWARDED=True`, we read the leftmost IP from
`X-Forwarded-For` instead. The leftmost is the original client because
each hop *appends* its own IP. We only do this when the operator
confirms the topology — if the app is exposed directly to the internet,
the header is attacker-controlled and would let anyone bypass limits.

In-memory by default. For true enforcement across multiple Cloud Run
instances, point slowapi at Redis (see `docs/HARDENING.md`).
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()


def _client_ip(request: Request) -> str:
    """Real-client key, taking `X-Forwarded-For` into account when trusted."""
    if settings.RATE_LIMIT_TRUST_FORWARDED:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # `client, proxy1, proxy2` — leftmost is the original client.
            return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)
