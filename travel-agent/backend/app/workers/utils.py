"""Shared worker utilities."""
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in km between two lat/lng points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _score_wishlist_fit(
    item: dict,
    available_window_mins: int,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
) -> float:
    """Score a wishlist item's fit for an available time window.

    Args:
        item: Wishlist item dict (as returned by get_wishlist tool).
        available_window_mins: Free time window in minutes.
        user_lat: User's current latitude, or None if unknown.
        user_lng: User's current longitude, or None if unknown.

    Returns:
        Float score 0.0–1.0. Higher is better fit.
    """
    estimated_mins = item.get("estimated_duration_mins") or 0

    # Time fit: 1.0 if item fits in window, else 0.0
    time_score = 1.0 if (estimated_mins > 0 and estimated_mins <= available_window_mins) else 0.0

    # Proximity fit: haversine-based if we have GPS coords for both user and item
    item_lat = None
    item_lng = None
    if isinstance(item.get("location"), dict):
        item_lat = item["location"].get("lat")
        item_lng = item["location"].get("lng")

    if user_lat is not None and user_lng is not None and item_lat is not None and item_lng is not None:
        km = _haversine_km(user_lat, user_lng, float(item_lat), float(item_lng))
        # 1.0 at 0 km, decays to ~0.5 at 5 km, ~0.1 at 20 km
        proximity_score = 1.0 / (1.0 + km / 5.0)
    else:
        proximity_score = 1.0  # unknown location — no penalty

    return time_score * proximity_score


async def inject_system_message(trip_id: int, content: str) -> None:
    """Append a [SYSTEM] message to a trip's conversation history.

    Workers use this to notify the agent of external events (flight changes,
    booking confirmations, scheduled briefings). The agent is instructed in
    its system prompt to process [SYSTEM] messages immediately and naturally.

    Creates its own DB session — safe to call from any worker context.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.trip_id == trip_id)
            )
            conv = result.scalar_one_or_none()
            if not conv:
                conv = Conversation(trip_id=trip_id, messages=[])
                db.add(conv)
                await db.flush()

            messages = list(conv.messages)
            messages.append(
                {
                    "role": "user",
                    "content": f"[SYSTEM] {content}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            conv.messages = messages
            await db.commit()
            logger.info("Injected system message for trip %d", trip_id)
    except Exception:
        logger.exception("Failed to inject system message for trip %d", trip_id)
