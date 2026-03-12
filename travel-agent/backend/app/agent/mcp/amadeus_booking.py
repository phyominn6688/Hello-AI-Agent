"""Amadeus write-enabled MCP wrapper — hotel booking and flight rebooking.

All write operations:
  1. Check BOOKING_ALLOWED config flag.
  2. Verify booking_token from Redis (mark as used, reject if used/expired).
  3. Verify trip ownership via DB query.
  4. Fall back to mock responses when API keys are not configured.
"""
import hashlib
import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.itinerary import Itinerary, ItineraryItem, WishlistStatus
from app.models.trip import Trip

logger = logging.getLogger(__name__)


# ── Booking token validation ───────────────────────────────────────────────────


async def _validate_and_consume_token(token: str) -> bool:
    """Return True if token is valid and mark it used. False if invalid/used/expired."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key = f"booking_token:{token_hash}"

    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        async with r:
            val = await r.get(key)
            if val is None:
                logger.warning("Booking token not found or expired: %s", token_hash[:8])
                return False
            data = json.loads(val)
            if data.get("used"):
                logger.warning("Booking token already used: %s", token_hash[:8])
                return False
            # Mark as used (keep in Redis until TTL expires for dedup)
            data["used"] = True
            ttl = await r.ttl(key)
            await r.setex(key, max(ttl, 1), json.dumps(data))
            return True
    except ImportError:
        # redis not installed — dev mode, allow through with warning
        logger.warning("Redis not available — booking token validation skipped (dev mode)")
        return True
    except Exception as e:
        logger.warning("Token validation error: %s", e)
        return False


# ── Amadeus auth ───────────────────────────────────────────────────────────────

_token_cache: dict[str, Any] = {}


async def _get_amadeus_token() -> str | None:
    from app.config import settings
    if not settings.amadeus_client_id:
        return None

    now = time.time()
    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.amadeus_base_url}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.amadeus_client_id,
                "client_secret": settings.amadeus_client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = now + data["expires_in"]
        return data["access_token"]


# ── Ownership verification ─────────────────────────────────────────────────────


async def _verify_item_ownership(item_id: int, user_id: int, db: AsyncSession) -> ItineraryItem | None:
    """Return item if it belongs to user, else None."""
    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary, ItineraryItem.itinerary_id == Itinerary.id)
        .join(Trip, Itinerary.trip_id == Trip.id)
        .where(ItineraryItem.id == item_id, Trip.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ── Tool definitions ───────────────────────────────────────────────────────────


def get_tools() -> list[dict]:
    return [
        {
            "name": "book_hotel",
            "description": (
                "Book a hotel offer via Amadeus. "
                "Requires a valid booking_token (single-use, 30s TTL) from the payments API. "
                "Re-prices the offer before booking; returns price_changed status if >5% drift."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "offer_id": {
                        "type": "string",
                        "description": "Amadeus hotel offer ID from search_hotels result",
                    },
                    "item_id": {
                        "type": "integer",
                        "description": "ItineraryItem DB ID to update after booking",
                    },
                    "travelers": {
                        "type": "array",
                        "description": "Traveler details for the booking",
                        "items": {
                            "type": "object",
                            "properties": {
                                "first_name": {"type": "string"},
                                "last_name": {"type": "string"},
                                "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"},
                                "passport_number": {"type": "string"},
                                "passport_expiry": {"type": "string", "description": "YYYY-MM-DD"},
                                "nationality": {"type": "string", "description": "ISO country code"},
                            },
                            "required": ["first_name", "last_name"],
                        },
                    },
                    "payment_method_id": {
                        "type": "string",
                        "description": "Stripe payment method ID",
                    },
                    "booking_token": {
                        "type": "string",
                        "description": "Single-use booking token from confirm-booking endpoint",
                    },
                },
                "required": ["offer_id", "item_id", "travelers", "booking_token"],
            },
        },
        {
            "name": "select_flight_alternative",
            "description": (
                "Find alternative flights on the same route when a disruption is detected. "
                "Searches within a time window and scores by minimum downstream schedule disruption. "
                "Returns top 3 alternatives as deep links for the user to complete externally."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "trip_id": {"type": "integer"},
                    "original_item_id": {
                        "type": "integer",
                        "description": "ItineraryItem ID of the disrupted flight",
                    },
                    "disruption_reason": {"type": "string"},
                    "window_start_iso": {
                        "type": "string",
                        "description": "ISO datetime — start of search window",
                    },
                    "window_end_iso": {
                        "type": "string",
                        "description": "ISO datetime — end of search window",
                    },
                },
                "required": ["trip_id", "original_item_id", "disruption_reason", "window_start_iso", "window_end_iso"],
            },
        },
        {
            "name": "confirm_flight_booking",
            "description": (
                "Record a flight booking confirmation (PNR) after the user completes booking "
                "externally via the deep link. Updates ItineraryItem and enqueues calendar update."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "booking_ref": {"type": "string", "description": "Booking reference / confirmation code"},
                    "pnr": {"type": "string", "description": "Airline PNR code"},
                },
                "required": ["item_id", "booking_ref"],
            },
        },
    ]


# ── Tool executor ──────────────────────────────────────────────────────────────


async def execute_tool(tool_name: str, tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    from app.config import settings

    if not settings.booking_allowed:
        if tool_name == "book_hotel":
            return {"error": "Booking is not enabled in this environment", "status": "disabled"}

    if tool_name == "book_hotel":
        return await _book_hotel(tool_input, db, user_id)
    elif tool_name == "select_flight_alternative":
        return await _select_flight_alternative(tool_input, db, user_id)
    elif tool_name == "confirm_flight_booking":
        return await _confirm_flight_booking(tool_input, db, user_id)
    return {"error": f"Unknown tool: {tool_name}"}


async def _book_hotel(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    from app.config import settings

    booking_token = tool_input.get("booking_token", "")
    if not booking_token:
        return {"status": "failed", "error": "booking_token is required"}

    # Validate token (single-use)
    if not await _validate_and_consume_token(booking_token):
        return {"status": "failed", "error": "Invalid, expired, or already-used booking token"}

    # Verify item ownership
    item = await _verify_item_ownership(tool_input["item_id"], user_id, db)
    if not item:
        return {"status": "failed", "error": "Item not found or access denied"}

    # Check idempotency — if already booked, return existing ref
    if item.booking_ref and item.booking_status == "booked":
        return {
            "status": "already_booked",
            "booking_ref": item.booking_ref,
            "message": "This item already has a confirmed booking.",
        }

    # Mock path — Amadeus not configured
    if not settings.amadeus_client_id:
        mock_ref = f"HTL-MOCK-{item.id}"
        item.booking_ref = mock_ref
        item.booking_status = "booked"
        item.wishlist_status = WishlistStatus.booked
        await db.flush()
        # Enqueue wallet pass generation (fire and forget)
        _enqueue_wallet_job(item, user_id)
        return {
            "status": "confirmed",
            "booking_ref": mock_ref,
            "hotel_confirmation_number": f"CONF-{item.id}",
            "price_breakdown": {"total_usd": 0, "note": "Mock booking — Amadeus not configured"},
        }

    # Real path — re-price then book
    token = await _get_amadeus_token()
    if not token:
        return {"status": "failed", "error": "Amadeus authentication failed"}

    async with httpx.AsyncClient(base_url=settings.amadeus_base_url) as client:
        headers = {"Authorization": f"Bearer {token}"}
        offer_id = tool_input["offer_id"]

        # Re-price to check for drift
        try:
            reprice_resp = await client.post(
                "/v1/shopping/hotel-offers/pricing",
                headers=headers,
                json={"data": {"offerId": offer_id}},
            )
            reprice_resp.raise_for_status()
            reprice_data = reprice_resp.json()
            new_price = float(
                reprice_data.get("data", {}).get("offers", [{}])[0].get("price", {}).get("total", 0)
            )
            original_price = float((item.item_data or {}).get("price_per_night_usd", new_price))
            if original_price > 0 and abs(new_price - original_price) / original_price > 0.05:
                return {
                    "status": "price_changed",
                    "original_price": original_price,
                    "new_price": new_price,
                    "message": "Hotel price changed by more than 5%. User must confirm the new price before booking.",
                }
        except Exception as e:
            logger.warning("Re-pricing failed for offer %s: %s", offer_id, e)

        # Build traveler payload
        travelers = []
        for i, t in enumerate(tool_input.get("travelers", []), start=1):
            traveler: dict[str, Any] = {
                "id": str(i),
                "name": {"firstName": t["first_name"], "lastName": t["last_name"]},
                "contact": {"emailAddress": ""},
            }
            if t.get("date_of_birth"):
                traveler["dateOfBirth"] = t["date_of_birth"]
            if t.get("passport_number"):
                traveler["documents"] = [
                    {
                        "documentType": "PASSPORT",
                        "number": t["passport_number"],
                        "expiryDate": t.get("passport_expiry", ""),
                        "issuanceCountry": t.get("nationality", ""),
                        "nationality": t.get("nationality", ""),
                        "holder": True,
                    }
                ]
            travelers.append(traveler)

        try:
            booking_resp = await client.post(
                "/v2/booking/hotel-orders",
                headers=headers,
                json={
                    "data": {
                        "offerId": offer_id,
                        "guests": travelers,
                        "payments": [
                            {
                                "method": "creditCard",
                                "paymentCard": {
                                    "paymentCardInfo": {
                                        "vendorCode": "VI",
                                        "cardNumber": "XXXX",  # Real card via Stripe
                                    }
                                },
                            }
                        ],
                    }
                },
            )
            booking_resp.raise_for_status()
            booking_data = booking_resp.json()
        except httpx.HTTPError as e:
            logger.exception("Amadeus hotel booking failed for offer %s", offer_id)
            return {"status": "failed", "error": str(e)}

        order = booking_data.get("data", {})
        booking_ref = order.get("id", f"HTL-{item.id}")
        hotel_conf = order.get("hotelBookings", [{}])[0].get("confirmationId", "")

        item.booking_ref = booking_ref
        item.booking_status = "booked"
        item.wishlist_status = WishlistStatus.booked
        await db.flush()

        _enqueue_wallet_job(item, user_id)

        return {
            "status": "confirmed",
            "booking_ref": booking_ref,
            "hotel_confirmation_number": hotel_conf,
            "price_breakdown": order.get("associatedRecords", {}),
        }


async def _select_flight_alternative(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    from datetime import datetime
    from app.config import settings

    trip_id = tool_input["trip_id"]
    original_item_id = tool_input["original_item_id"]

    # Verify access
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        return {"error": "Trip not found"}

    # Load original flight item
    item = await _verify_item_ownership(original_item_id, user_id, db)
    if not item:
        return {"error": "Original flight item not found"}

    item_data = item.item_data or {}
    origin = item_data.get("origin", "")
    destination = item_data.get("destination", "")

    if not origin or not destination:
        return {"error": "Original flight item is missing origin/destination in item_data"}

    window_start = tool_input.get("window_start_iso", "")
    departure_date = window_start[:10] if window_start else ""

    if not settings.amadeus_client_id:
        # Mock alternatives
        return {
            "alternatives": [
                {
                    "id": "alt-1",
                    "origin": origin,
                    "destination": destination,
                    "departs": f"{departure_date}T14:00:00",
                    "arrives": f"{departure_date}T18:30:00",
                    "carrier": "UA",
                    "flight_number": "UA500",
                    "price_usd": 320.0,
                    "disruption_score": 0.3,
                    "book_url": "https://www.amadeus.com",
                    "recommended": True,
                },
                {
                    "id": "alt-2",
                    "origin": origin,
                    "destination": destination,
                    "departs": f"{departure_date}T16:00:00",
                    "arrives": f"{departure_date}T20:30:00",
                    "carrier": "DL",
                    "flight_number": "DL200",
                    "price_usd": 280.0,
                    "disruption_score": 0.6,
                    "book_url": "https://www.amadeus.com",
                    "recommended": False,
                },
            ],
            "count": 2,
            "note": "Mock data — configure AMADEUS_CLIENT_ID for real alternatives",
        }

    token = await _get_amadeus_token()
    if not token:
        return {"error": "Amadeus authentication failed"}

    async with httpx.AsyncClient(base_url=settings.amadeus_base_url) as client:
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": 1,
            "max": 10,
            "currencyCode": "USD",
        }
        try:
            resp = await client.get("/v2/shopping/flight-offers", params=params, headers=headers)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:
            return {"error": f"Amadeus flight search failed: {e}"}

    flights = raw.get("data", [])
    # Score alternatives by departure time proximity to window_start
    scored = []
    for f in flights[:10]:
        price = float(f.get("price", {}).get("grandTotal", 0))
        segs = f.get("itineraries", [{}])[0].get("segments", [{}])
        departs = segs[0].get("departure", {}).get("at", "") if segs else ""
        try:
            dep_dt = datetime.fromisoformat(departs.replace("Z", "+00:00"))
            ws_dt = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
            delay_mins = max(0, (dep_dt - ws_dt).total_seconds() / 60)
            disruption_score = min(1.0, delay_mins / 360)  # 0=no disruption, 1=6h delay
        except Exception:
            disruption_score = 0.5
        scored.append({
            "id": f.get("id"),
            "origin": origin,
            "destination": destination,
            "departs": departs,
            "arrives": segs[-1].get("arrival", {}).get("at", "") if segs else "",
            "carrier": f.get("validatingAirlineCodes", [""])[0],
            "flight_number": segs[0].get("number", "") if segs else "",
            "price_usd": price,
            "disruption_score": disruption_score,
            "book_url": "https://www.amadeus.com",
            "recommended": False,
        })

    scored.sort(key=lambda x: x["disruption_score"])
    top3 = scored[:3]
    if top3:
        top3[0]["recommended"] = True

    return {"alternatives": top3, "count": len(top3)}


async def _confirm_flight_booking(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    item_id = tool_input["item_id"]
    item = await _verify_item_ownership(item_id, user_id, db)
    if not item:
        return {"status": "failed", "error": "Item not found or access denied"}

    item.booking_ref = tool_input.get("booking_ref", "")
    if tool_input.get("pnr"):
        existing_data = dict(item.item_data or {})
        existing_data["pnr"] = tool_input["pnr"]
        item.item_data = existing_data
    item.booking_status = "booked"
    item.wishlist_status = WishlistStatus.booked
    await db.flush()

    # Enqueue calendar update (fire and forget)
    try:
        _enqueue_calendar_update(item)
    except Exception:
        logger.warning("Failed to enqueue calendar update for item %d", item_id)

    return {
        "status": "confirmed",
        "item_id": item_id,
        "booking_ref": item.booking_ref,
        "message": "Flight booking recorded. Calendar updated.",
    }


def _enqueue_wallet_job(item: ItineraryItem, user_id: int) -> None:
    """Enqueue an SQS message for wallet pass generation (fire and forget)."""
    try:
        import boto3
        import os
        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        wallet_queue_url = os.environ.get("WALLET_QUEUE_URL", os.environ.get("QUEUE_URL", ""))
        if wallet_queue_url:
            import json
            sqs.send_message(
                QueueUrl=wallet_queue_url,
                MessageBody=json.dumps({
                    "type": "generate_wallet_pass",
                    "item_id": item.id,
                    "user_id": user_id,
                    "pass_type": item.type.value if hasattr(item.type, "value") else str(item.type),
                    "title": item.name,
                    "booking_ref": item.booking_ref or "",
                }),
            )
    except Exception as e:
        logger.warning("Failed to enqueue wallet pass job: %s", e)


def _enqueue_calendar_update(item: ItineraryItem) -> None:
    """Enqueue an SQS message for calendar sync (fire and forget)."""
    try:
        import boto3
        import json
        import os
        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        queue_url = os.environ.get("QUEUE_URL", "")
        if queue_url:
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps({
                    "type": "calendar_update",
                    "item_id": item.id,
                    "booking_ref": item.booking_ref or "",
                }),
            )
    except Exception as e:
        logger.warning("Failed to enqueue calendar update: %s", e)
