"""Shared worker utilities."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)


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
