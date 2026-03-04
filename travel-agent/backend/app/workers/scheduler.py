"""Background worker — guide mode scheduler.

Triggers proactive nudges:
- Morning briefing at 7am local time
- Leave-now alerts based on travel time + buffer
- Pre-departure reminders (24h, 2h before flights)
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("Scheduler worker started")
    while True:
        try:
            await _check_active_trips()
        except Exception:
            logger.exception("Scheduler loop error")
        # Check every 5 minutes
        await asyncio.sleep(300)


async def _check_active_trips() -> None:
    """Find active trips and queue appropriate notifications."""
    from datetime import date, datetime, timezone

    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.models.itinerary import Itinerary, ItineraryItem
    from app.models.trip import Trip, TripStatus

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trip).where(Trip.status == TripStatus.active)
        )
        active_trips = result.scalars().all()

        for trip in active_trips:
            today = date.today()
            result = await db.execute(
                select(Itinerary).where(
                    Itinerary.trip_id == trip.id, Itinerary.date == today
                )
            )
            itin = result.scalar_one_or_none()
            if itin:
                await _check_leave_now_alerts(trip, itin)


async def _check_leave_now_alerts(trip, itin) -> None:
    """Check if it's time to send a leave-now alert for any fixed events."""
    from datetime import datetime, time, timezone

    from sqlalchemy.orm import selectinload

    from app.db.database import AsyncSessionLocal
    from app.models.itinerary import Flexibility, ItineraryItem
    from app.workers.notifier import send_push_notification

    now = datetime.now(timezone.utc).time()
    # Implementation: compare now vs (item.start_time - transit_buffer_mins)
    # For now this is a stub — Iteration 2 adds real directions + timing
    logger.debug(f"Checked leave-now alerts for trip {trip.id}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
