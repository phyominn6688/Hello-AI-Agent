"""Background scheduler — guide mode proactive nudges.

Runs every 5 minutes. Triggers:
- Morning briefing at ~7am destination time (UTC approximation for first draft;
  TODO: use Destination.timezone field when added in a future iteration)
- Pre-departure reminders: 24h and 2h before fixed flights
- Leave-now alerts: when it's time to depart for a fixed event

All notifications are delivered via:
  1. Alert row in the database (shown in AlertBanner)
  2. SNS push notification
  3. [SYSTEM] message injected into the conversation (agent re-engagement)
"""
import asyncio
import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.models.itinerary import Alert, Flexibility, Itinerary, ItineraryItem, ItemType
from app.models.trip import Trip, TripStatus
from app.models.user import User
from app.workers.notifier import send_push_notification
from app.workers.utils import inject_system_message

logger = logging.getLogger(__name__)

# ── Haversine distance ─────────────────────────────────────────────────────────


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _estimate_transit_mins(user_lat: float, user_lng: float, dest_lat: float, dest_lng: float) -> int:
    """Rough transit estimate: walking speed ~5 km/h + 5 min buffer."""
    km = _haversine_km(user_lat, user_lng, dest_lat, dest_lng)
    walking_mins = (km / 5.0) * 60
    return max(10, int(walking_mins) + 5)


# ── Alert deduplication ────────────────────────────────────────────────────────


async def _alert_exists(db, trip_id: int, user_id: int, alert_type: str, since: datetime) -> bool:
    result = await db.execute(
        select(Alert).where(
            Alert.trip_id == trip_id,
            Alert.user_id == user_id,
            Alert.type == alert_type,
            Alert.created_at >= since,
        )
    )
    return result.scalar_one_or_none() is not None


async def _create_alert(db, trip_id: int, user_id: int, alert_type: str, message: str) -> None:
    alert = Alert(trip_id=trip_id, user_id=user_id, type=alert_type, message=message)
    db.add(alert)
    await db.flush()


# ── Morning briefing ───────────────────────────────────────────────────────────


async def _check_morning_briefing(db, trip: Trip, user: User, today: date) -> None:
    """Send morning briefing once per day for active trips.

    Triggers between 06:00–08:00 UTC. TODO: use destination timezone when
    Destination.timezone field is added.
    """
    now_utc = datetime.now(timezone.utc)
    if not (6 <= now_utc.hour < 8):
        return

    day_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    if await _alert_exists(db, trip.id, user.id, "morning_briefing", day_start):
        return

    await _create_alert(
        db, trip.id, user.id, "morning_briefing",
        f"Good morning! Your daily briefing for {today.strftime('%A, %B %d')} is ready.",
    )
    await send_push_notification(
        user.id, trip.id,
        f"Good morning! Tap to see your briefing for today.",
        "morning_briefing",
    )
    await inject_system_message(
        trip.id,
        "Morning briefing time. Generate a warm, concise morning briefing covering: "
        "today's scheduled activities, current weather conditions (use get_weather tool), "
        "any time-sensitive items or fixed events, and one practical tip for the day. "
        "Keep it brief and energising — the traveler is starting their day.",
    )
    logger.info("Sent morning briefing for trip %d", trip.id)


# ── Pre-departure reminders ────────────────────────────────────────────────────


async def _check_predeparture_reminders(db, trip: Trip, user: User, today: date) -> None:
    """Send reminders 24h and 2h before fixed flights."""
    result = await db.execute(
        select(Itinerary)
        .options(selectinload(Itinerary.items))
        .where(Itinerary.trip_id == trip.id)
    )
    itineraries = result.scalars().all()

    now_utc = datetime.now(timezone.utc)

    for itin in itineraries:
        for item in itin.items:
            if item.type != ItemType.flight:
                continue
            if item.flexibility != Flexibility.fixed:
                continue
            if not item.start_time:
                continue

            # Combine itinerary date + start_time to get departure datetime (naive UTC assumption)
            departure_dt = datetime.combine(itin.date, item.start_time, tzinfo=timezone.utc)
            delta = departure_dt - now_utc

            for hours, label in [(24, "24h"), (2, "2h")]:
                window = timedelta(hours=hours)
                if timedelta(minutes=-15) <= (delta - window) <= timedelta(minutes=15):
                    alert_type = f"reminder_{label}_{item.id}"
                    day_start = now_utc - timedelta(hours=1)
                    if await _alert_exists(db, trip.id, user.id, "reminder", day_start):
                        continue

                    msg = (
                        f"{label} until your flight {item.name}. "
                        f"Departing {departure_dt.strftime('%H:%M')} UTC."
                    )
                    await _create_alert(db, trip.id, user.id, "reminder", msg)
                    await send_push_notification(user.id, trip.id, msg, "reminder")
                    await inject_system_message(
                        trip.id,
                        f"Pre-departure reminder: {item.name} departs in {hours} hours "
                        f"({departure_dt.strftime('%H:%M')} UTC). "
                        f"Run through the pre-departure checklist: confirm check-in status, "
                        f"remind about airport transit time, verify documents are ready, "
                        f"and check for any last-minute gate changes.",
                    )
                    logger.info("Sent %s reminder for item %d (trip %d)", label, item.id, trip.id)


# ── Leave-now alerts ───────────────────────────────────────────────────────────


async def _check_leave_now_alerts(db, trip: Trip, user: User, today: date) -> None:
    """Alert when it's time to leave for a fixed event."""
    result = await db.execute(
        select(Itinerary)
        .options(selectinload(Itinerary.items))
        .where(Itinerary.trip_id == trip.id, Itinerary.date == today)
    )
    itin = result.scalar_one_or_none()
    if not itin:
        return

    now_utc = datetime.now(timezone.utc)
    now_time = now_utc.time()

    for item in itin.items:
        if item.flexibility != Flexibility.fixed:
            continue
        if not item.start_time:
            continue

        # Estimate transit time
        transit_mins = 30  # default
        if (
            user.current_lat and user.current_lng
            and item.location
            and item.location.get("lat") and item.location.get("lng")
        ):
            transit_mins = _estimate_transit_mins(
                user.current_lat, user.current_lng,
                item.location["lat"], item.location["lng"],
            )

        buffer_mins = 15
        leave_dt = datetime.combine(today, item.start_time, tzinfo=timezone.utc) - timedelta(minutes=transit_mins + buffer_mins)

        # Trigger within a 5-min window of leave time
        if leave_dt <= now_utc <= leave_dt + timedelta(minutes=5):
            alert_key = f"leave_now_{item.id}"
            day_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
            if await _alert_exists(db, trip.id, user.id, "leave_now", day_start):
                continue

            msg = (
                f"Time to leave for {item.name}! "
                f"Estimated {transit_mins} min travel — departs {item.start_time.strftime('%H:%M')}."
            )
            await _create_alert(db, trip.id, user.id, "leave_now", msg)
            await send_push_notification(user.id, trip.id, msg, "leave_now")
            await inject_system_message(
                trip.id,
                f"Leave-now alert triggered for {item.name} (starts {item.start_time}). "
                f"Estimated transit time: {transit_mins} minutes. "
                f"Tell the traveler it's time to leave, give the quickest route "
                f"(use get_directions if user location is available), and note any relevant tips.",
            )
            logger.info("Sent leave-now alert for item %d (trip %d)", item.id, trip.id)


# ── Main loop ──────────────────────────────────────────────────────────────────


async def _check_active_trips() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trip)
            .options(selectinload(Trip.destinations))
            .where(Trip.status == TripStatus.active)
        )
        active_trips = result.scalars().all()

        for trip in active_trips:
            result = await db.execute(select(User).where(User.id == trip.user_id))
            user = result.scalar_one_or_none()
            if not user:
                continue

            today = date.today()
            try:
                await _check_morning_briefing(db, trip, user, today)
                await _check_predeparture_reminders(db, trip, user, today)
                await _check_leave_now_alerts(db, trip, user, today)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Scheduler error for trip %d", trip.id)


async def run() -> None:
    logger.info("Scheduler worker started")
    while True:
        try:
            await _check_active_trips()
        except Exception:
            logger.exception("Scheduler loop error")
        await asyncio.sleep(300)  # 5 minutes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
