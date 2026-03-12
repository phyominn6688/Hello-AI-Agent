"""Background worker — polls flight status and triggers cascade replanning.

Runs as a separate ECS task consuming from the SQS queue.
Zero FastAPI dependency — runs standalone.

Message format expected on the queue:
  {
    "type": "flight_status_check",
    "trip_id": 123,
    "item_id": 456,
    "user_id": 789,
    "flight_number": "UA123",
    "carrier_code": "UA",
    "flight_num": "123",
    "scheduled_date": "2026-03-14",
    "booking_ref": "ABC123"
  }
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.db.database import AsyncSessionLocal
from app.models.itinerary import Alert, ItineraryItem
from app.workers.notifier import send_push_notification
from app.workers.utils import inject_system_message

logger = logging.getLogger(__name__)
QUEUE_URL = os.environ.get("QUEUE_URL", "http://localhost:4566/000000000000/travel-agent")

# ── Amadeus auth ───────────────────────────────────────────────────────────────


async def _get_amadeus_token() -> Optional[str]:
    from app.config import settings

    if not settings.amadeus_client_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.amadeus_base_url}/v1/security/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.amadeus_client_id,
                    "client_secret": settings.amadeus_client_secret,
                },
            )
            resp.raise_for_status()
            return resp.json().get("access_token")
    except Exception as e:
        logger.warning("Amadeus auth failed: %s", e)
        return None


# ── Flight status check ────────────────────────────────────────────────────────


async def _fetch_flight_status(
    carrier_code: str,
    flight_num: str,
    scheduled_date: str,
    token: str,
) -> Optional[dict]:
    from app.config import settings

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.amadeus_base_url}/v2/schedule/flights",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "carrierCode": carrier_code,
                    "flightNumber": flight_num,
                    "scheduledDepartureDate": scheduled_date,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            flights = data.get("data", [])
            if flights:
                return flights[0]
    except Exception as e:
        logger.warning("Amadeus flight status fetch failed: %s", e)
    return None


def _parse_status(flight_data: dict) -> dict:
    """Extract status and delay from Amadeus flight schedule response."""
    segments = flight_data.get("flightPoints", [])
    departure = next((s for s in segments if s.get("departure")), {})
    dep_info = departure.get("departure", {})
    timings = dep_info.get("timings", [])

    scheduled_time = next(
        (t["value"] for t in timings if t.get("qualifier") == "STD"), None
    )
    estimated_time = next(
        (t["value"] for t in timings if t.get("qualifier") == "ETD"), None
    )

    status = flight_data.get("flightDesignator", {})
    return {
        "carrier": status.get("carrierCode", ""),
        "flight_number": status.get("flightNumber", ""),
        "scheduled_departure": scheduled_time,
        "estimated_departure": estimated_time,
        "delay_mins": _calc_delay(scheduled_time, estimated_time),
    }


def _calc_delay(scheduled: Optional[str], estimated: Optional[str]) -> int:
    if not scheduled or not estimated:
        return 0
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        s = datetime.strptime(scheduled[:19], fmt)
        e = datetime.strptime(estimated[:19], fmt)
        return max(0, int((e - s).total_seconds() / 60))
    except Exception:
        return 0


# ── Alternative flight search ──────────────────────────────────────────────────


async def _search_flight_alternatives(body: dict, status_data: dict, delay_mins: int) -> dict:
    """Search for alternative flights on the same route within the next 6 hours."""
    from datetime import datetime, timezone, timedelta
    from app.config import settings

    item_data = body.get("item_data", {})
    origin = item_data.get("origin", "")
    destination = item_data.get("destination", "")
    scheduled_date = body.get("scheduled_date", "")

    if not (origin and destination and scheduled_date):
        return {}

    token = await _get_amadeus_token()
    if not token:
        # Return mock alternatives if no Amadeus token
        return {
            "alternatives": [
                {
                    "id": "alt-mock-1",
                    "origin": origin,
                    "destination": destination,
                    "departs": f"{scheduled_date}T18:00:00",
                    "carrier": "UA",
                    "flight_number": "UA999",
                    "price_usd": 350.0,
                    "disruption_score": 0.3,
                    "book_url": "https://www.amadeus.com",
                    "recommended": True,
                }
            ]
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.amadeus_base_url}/v2/shopping/flight-offers",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "departureDate": scheduled_date,
                    "adults": 1,
                    "max": 10,
                    "currencyCode": "USD",
                },
            )
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        logger.warning("Alternative flight search failed: %s", e)
        return {}

    flights = raw.get("data", [])
    estimated_dep = status_data.get("estimated_departure", "")

    scored = []
    for f in flights[:10]:
        price = float(f.get("price", {}).get("grandTotal", 0))
        segs = f.get("itineraries", [{}])[0].get("segments", [{}])
        departs = segs[0].get("departure", {}).get("at", "") if segs else ""
        try:
            dep_dt = datetime.fromisoformat(departs.replace("Z", "+00:00"))
            if estimated_dep:
                ref_dt = datetime.fromisoformat(estimated_dep.replace("Z", "+00:00"))
            else:
                ref_dt = datetime.now(timezone.utc)
            delay_mins_from_disruption = max(0, (dep_dt - ref_dt).total_seconds() / 60)
            disruption_score = min(1.0, delay_mins_from_disruption / 360)
        except Exception:
            disruption_score = 0.5

        scored.append({
            "id": f.get("id"),
            "origin": origin,
            "destination": destination,
            "departs": departs,
            "carrier": f.get("validatingAirlineCodes", [""])[0],
            "flight_number": (segs[0].get("number", "") if segs else ""),
            "price_usd": price,
            "disruption_score": disruption_score,
            "book_url": "https://www.amadeus.com",
            "recommended": False,
        })

    scored.sort(key=lambda x: x["disruption_score"])
    top3 = scored[:3]
    if top3:
        top3[0]["recommended"] = True

    return {"alternatives": top3}


async def _process_proactive_rebook_search(message_body: dict) -> None:
    """Handle proactive_rebook_search SQS message — search and inject without disruption preamble."""
    trip_id = message_body.get("trip_id")
    item_id = message_body.get("item_id")

    if not trip_id:
        return

    alternatives = await _search_flight_alternatives(message_body, {}, 0)
    if not alternatives:
        return

    system_content = (
        f"Proactive rebooking search completed for item {item_id}. "
        f"Alternatives found: {json.dumps(alternatives)}. "
        f"Present these options to the traveler using the trade_off_options format "
        f"if they are relevant to any upcoming disruption."
    )
    await inject_system_message(trip_id, system_content)
    logger.info("Proactive rebook search injected for trip %d", trip_id)


# ── Message processing ─────────────────────────────────────────────────────────


async def process_flight_status_check(message: dict) -> None:
    body = json.loads(message.get("Body", "{}"))
    trip_id = body.get("trip_id")
    item_id = body.get("item_id")
    user_id = body.get("user_id")
    carrier_code = body.get("carrier_code", "")
    flight_num = body.get("flight_num", "")
    scheduled_date = body.get("scheduled_date", "")
    flight_number = body.get("flight_number", carrier_code + flight_num)

    logger.info("Checking flight status: %s (trip %s, item %s)", flight_number, trip_id, item_id)

    # Try to get real status from Amadeus
    status_data = None
    token = await _get_amadeus_token()
    if token and carrier_code and flight_num and scheduled_date:
        raw = await _fetch_flight_status(carrier_code, flight_num, scheduled_date, token)
        if raw:
            status_data = _parse_status(raw)

    if not status_data:
        # No API key or fetch failed — no change to report
        logger.debug("No status data for %s — skipping", flight_number)
        return

    delay_mins = status_data.get("delay_mins", 0)

    # Only act on meaningful delays (>= 30 min) or cancellations
    if delay_mins < 30:
        return

    alert_type = "cancellation" if delay_mins >= 720 else "flight_change"

    if delay_mins >= 120:
        # Major delay or cancellation — search for alternatives and inject as trade_off_options
        alternatives = await _search_flight_alternatives(
            body, status_data, delay_mins
        )
        alt_json = json.dumps(alternatives) if alternatives else "{}"

        if delay_mins >= 720:
            message_text = (
                f"Flight {flight_number} appears to be cancelled or severely delayed "
                f"({delay_mins} min). Immediate replanning required."
            )
            system_content = (
                f"REQUIRES_USER_DECISION: true\n"
                f"URGENT: Flight {flight_number} is cancelled or severely delayed ({delay_mins} min). "
                f"Immediately assess the full downstream impact on the itinerary and present "
                f"replanning options using the trade_off_options format. "
                f"Search for alternative flights, check hotel flexibility, and flag any cascading impacts.\n"
                f"Pre-searched alternatives: {alt_json}"
            )
        else:
            message_text = (
                f"Flight {flight_number} is delayed by {delay_mins} minutes. "
                f"New estimated departure: {status_data.get('estimated_departure', 'TBD')}."
            )
            system_content = (
                f"REQUIRES_USER_DECISION: true\n"
                f"Flight {flight_number} is delayed by {delay_mins} minutes "
                f"(new departure: {status_data.get('estimated_departure', 'TBD')}). "
                f"This may cascade to downstream itinerary items. "
                f"Use select_flight_alternative to search for alternatives and present them "
                f"using the trade_off_options format.\n"
                f"Pre-searched alternatives: {alt_json}"
            )
    else:
        # Minor delay (30-119 min) — just alert, no alternatives search
        message_text = (
            f"Flight {flight_number} is delayed by {delay_mins} minutes. "
            f"New estimated departure: {status_data.get('estimated_departure', 'TBD')}."
        )
        system_content = (
            f"Flight {flight_number} is delayed by {delay_mins} minutes "
            f"(new departure: {status_data.get('estimated_departure', 'TBD')}). "
            f"Assess impact on the rest of today's itinerary — check connections, "
            f"hotel check-in times, and any fixed events. "
            f"If the delay causes a cascade, present replanning options."
        )

    # Persist alert and update item status
    async with AsyncSessionLocal() as db:
        try:
            if item_id:
                from sqlalchemy import select as sa_select
                result = await db.execute(
                    sa_select(ItineraryItem).where(ItineraryItem.id == item_id)
                )
                item = result.scalar_one_or_none()
                if item:
                    item.booking_status = f"delayed_{delay_mins}min" if delay_mins < 720 else "cancelled"

            alert = Alert(
                trip_id=trip_id,
                user_id=user_id,
                type=alert_type,
                message=message_text,
            )
            db.add(alert)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to persist flight alert for trip %d", trip_id)

    await send_push_notification(user_id, trip_id, message_text, alert_type)
    await inject_system_message(trip_id, system_content)
    logger.info("Flight alert sent for %s (trip %d): %d min delay", flight_number, trip_id, delay_mins)


# ── SQS helpers ────────────────────────────────────────────────────────────────


async def _receive_messages() -> list[dict]:
    try:
        import boto3

        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            MessageAttributeNames=["All"],
        )
        return response.get("Messages", [])
    except Exception as e:
        logger.warning("SQS receive failed: %s", e)
        return []


async def _delete_message(receipt_handle: str) -> None:
    try:
        import boto3

        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
    except Exception as e:
        logger.warning("SQS delete failed: %s", e)


# ── Main loop ──────────────────────────────────────────────────────────────────


async def run() -> None:
    logger.info("Flight monitor worker started")
    while True:
        messages = await _receive_messages()
        for msg in messages:
            try:
                attrs = msg.get("MessageAttributes", {})
                msg_type = attrs.get("type", {}).get("StringValue", "")
                body_str = msg.get("Body", "{}")

                if msg_type == "flight_status_check":
                    await process_flight_status_check(msg)
                elif msg_type == "proactive_rebook_search":
                    body = json.loads(body_str)
                    await _process_proactive_rebook_search(body)
                else:
                    # Also check body for type field (some SQS producers set it there)
                    try:
                        body = json.loads(body_str)
                        body_type = body.get("type", "")
                        if body_type == "flight_status_check":
                            await process_flight_status_check(msg)
                        elif body_type == "proactive_rebook_search":
                            await _process_proactive_rebook_search(body)
                    except Exception:
                        pass

                await _delete_message(msg["ReceiptHandle"])
            except Exception:
                logger.exception("Failed to process message %s", msg.get("MessageId"))
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
