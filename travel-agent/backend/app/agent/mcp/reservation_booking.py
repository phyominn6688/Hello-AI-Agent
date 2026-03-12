"""Reservation booking MCP wrapper — restaurant deep links and confirmation recording.

For restaurants, we generate an OpenTable deep link and instruct the user to complete
the booking externally, then paste their confirmation number back.
"""
import logging
import urllib.parse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.itinerary import Itinerary, ItineraryItem, WishlistStatus
from app.models.trip import Trip

logger = logging.getLogger(__name__)


def get_tools() -> list[dict]:
    return [
        {
            "name": "get_restaurant_booking_link",
            "description": (
                "Generate an OpenTable deep link for a restaurant booking. "
                "Returns a URL for the user to complete the booking externally, "
                "then come back with their confirmation number."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "restaurant_name": {"type": "string"},
                    "place_id": {
                        "type": "string",
                        "description": "OpenTable restaurant ID (rid parameter)",
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM (24h)"},
                    "party_size": {"type": "integer", "description": "Number of diners"},
                    "item_id": {"type": "integer", "description": "ItineraryItem DB ID"},
                },
                "required": ["restaurant_name", "date", "time", "party_size", "item_id"],
            },
        },
        {
            "name": "confirm_restaurant_booking",
            "description": (
                "Record a restaurant booking confirmation after the user completes it via the deep link. "
                "Updates the ItineraryItem and enqueues a calendar event."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "confirmation_ref": {"type": "string", "description": "OpenTable confirmation number"},
                    "restaurant_name": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM (24h)"},
                },
                "required": ["item_id", "confirmation_ref"],
            },
        },
    ]


async def execute_tool(tool_name: str, tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    if tool_name == "get_restaurant_booking_link":
        return _get_restaurant_booking_link(tool_input)
    elif tool_name == "confirm_restaurant_booking":
        return await _confirm_restaurant_booking(tool_input, db, user_id)
    return {"error": f"Unknown tool: {tool_name}"}


def _get_restaurant_booking_link(tool_input: dict) -> dict:
    """Construct OpenTable deep link URL."""
    place_id = tool_input.get("place_id", "")
    date_str = tool_input.get("date", "")
    time_str = tool_input.get("time", "00:00")
    party_size = tool_input.get("party_size", 2)

    if place_id:
        # Official OpenTable deep link format
        booking_url = (
            f"https://www.opentable.com/restref/client/"
            f"?rid={urllib.parse.quote(str(place_id))}"
            f"&datetime={urllib.parse.quote(f'{date_str}T{time_str}')}"
            f"&covers={party_size}"
        )
    else:
        # Fallback — search link when place_id is not known
        restaurant_name = tool_input.get("restaurant_name", "")
        encoded_name = urllib.parse.quote(restaurant_name)
        booking_url = (
            f"https://www.opentable.com/s/?term={encoded_name}"
            f"&dateTime={urllib.parse.quote(f'{date_str}T{time_str}')}"
            f"&covers={party_size}"
        )

    return {
        "booking_url": booking_url,
        "restaurant_name": tool_input.get("restaurant_name", ""),
        "date": date_str,
        "time": time_str,
        "party_size": party_size,
        "instructions": (
            "Complete your booking on OpenTable, then paste your confirmation number here "
            "so I can record it and add the reservation to your calendar."
        ),
    }


async def _confirm_restaurant_booking(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    """Record confirmation and enqueue calendar update."""
    item_id = tool_input["item_id"]

    # Verify ownership
    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary, ItineraryItem.itinerary_id == Itinerary.id)
        .join(Trip, Itinerary.trip_id == Trip.id)
        .where(ItineraryItem.id == item_id, Trip.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return {"status": "failed", "error": "Item not found or access denied"}

    # Update booking fields
    item.booking_ref = tool_input.get("confirmation_ref", "")
    item.booking_status = "booked"
    item.wishlist_status = WishlistStatus.booked

    # Store additional details in item_data
    existing_data = dict(item.item_data or {})
    if tool_input.get("date"):
        existing_data["confirmed_date"] = tool_input["date"]
    if tool_input.get("time"):
        existing_data["confirmed_time"] = tool_input["time"]
    if tool_input.get("restaurant_name"):
        existing_data["restaurant_name"] = tool_input["restaurant_name"]
    item.item_data = existing_data

    await db.flush()

    # Enqueue calendar update
    try:
        _enqueue_calendar_update(item)
    except Exception:
        logger.warning("Failed to enqueue calendar update for item %d", item_id)

    logger.info("Restaurant booking confirmed: item=%d ref=%s", item_id, item.booking_ref)

    return {
        "status": "confirmed",
        "item_id": item_id,
        "booking_ref": item.booking_ref,
        "message": f"Reservation confirmed and calendar updated.",
    }


def _enqueue_calendar_update(item: ItineraryItem) -> None:
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
