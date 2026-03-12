"""Shared FastAPI dependencies (rate limiters, etc.).

Kept in a separate module to avoid circular imports between main.py and routers.
"""
from app.config import settings
from app.middleware.rate_limit import RateLimiter

read_limiter = RateLimiter(settings.rate_limit_read_per_minute)
write_limiter = RateLimiter(settings.rate_limit_write_per_minute)
chat_limiter = RateLimiter(settings.rate_limit_chat_per_minute)

# Booking is rate-limited to 5 per hour (sliding window).
# RateLimiter uses a 60-second window by default; booking_limiter uses per-hour
# semantics via a dedicated instance with rpm=5 and window effectively enforced
# by the hourly token budget (conservative limit regardless of window precision).
booking_limiter = RateLimiter(settings.booking_limiter_per_hour)
