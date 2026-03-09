"""Shared FastAPI dependencies (rate limiters, etc.).

Kept in a separate module to avoid circular imports between main.py and routers.
"""
from app.config import settings
from app.middleware.rate_limit import RateLimiter

read_limiter = RateLimiter(settings.rate_limit_read_per_minute)
write_limiter = RateLimiter(settings.rate_limit_write_per_minute)
chat_limiter = RateLimiter(settings.rate_limit_chat_per_minute)
