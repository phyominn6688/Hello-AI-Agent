"""Per-user rate limiting — applied as FastAPI dependencies on external-facing routes.

Uses an in-memory sliding window counter keyed by user sub (extracted from the JWT
without full verification — auth still happens in route handlers). Falls back to
client IP when no JWT is present.

NOTE: This in-memory store is per-process. In a multi-instance production deployment,
replace with a Redis-backed counter (e.g. INCR + EXPIRE on a per-user-per-minute key).
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from jose import jwt as jose_jwt


def _user_key(request: Request) -> str:
    """Extract a stable per-user key from the request.

    Tries to read the 'sub' claim from the JWT without signature verification
    (rate-limit bucketing only — authorization is still enforced in route handlers).
    Falls back to client IP.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            claims = jose_jwt.get_unverified_claims(auth_header[7:])
            sub = claims.get("sub", "")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


class RateLimiter:
    """Sliding-window rate limiter dependency.

    Usage:
        read_limiter = RateLimiter(settings.rate_limit_read_per_minute)

        @router.get("/resource")
        async def handler(..., _: None = Depends(read_limiter)):
            ...
    """

    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self._counters: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, request: Request) -> None:
        key = _user_key(request)
        now = time.monotonic()
        window_start = now - 60.0

        timestamps = self._counters[key]
        timestamps[:] = [t for t in timestamps if t > window_start]

        if len(timestamps) >= self.rpm:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": "60"},
            )

        timestamps.append(now)
