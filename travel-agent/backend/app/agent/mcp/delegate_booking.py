"""Delegate booking MCP wrapper — main agent calls this to invoke the booking sub-agent.

The main agent MUST have explicit user confirmation before calling this tool.
This module validates the request, loads traveler details, and delegates to
booking_agent.run_booking().
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.itinerary import Itinerary, ItineraryItem
from app.models.trip import Trip
from app.models.user import User

logger = logging.getLogger(__name__)


def get_tools() -> list[dict]:
    return [
        {
            "name": "delegate_booking",
            "description": (
                "Delegate a confirmed hotel booking to the booking sub-agent. "
                "ONLY call this after the user has explicitly confirmed (e.g. 'yes, book it'). "
                "Requires a valid booking_token from the payments API. "
                "For flights and restaurants, use select_flight_alternative or "
                "get_restaurant_booking_link instead (external booking via deep link)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "integer",
                        "description": "ItineraryItem DB ID to book",
                    },
                    "booking_type": {
                        "type": "string",
                        "enum": ["hotel"],
                        "description": "Type of booking to execute",
                    },
                    "offer_id": {
                        "type": "string",
                        "description": "Provider offer ID (Amadeus hotel offer ID)",
                    },
                    "offer_snapshot": {
                        "type": "object",
                        "description": "Snapshot of the offer details at time of confirmation",
                    },
                    "user_confirmed": {
                        "type": "boolean",
                        "description": "MUST be true — set only after explicit user confirmation",
                    },
                    "booking_token": {
                        "type": "string",
                        "description": "Single-use booking token from POST /api/v1/payments/confirm-booking",
                    },
                },
                "required": ["item_id", "booking_type", "offer_id", "user_confirmed", "booking_token"],
            },
        }
    ]


async def execute_tool(tool_name: str, tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    if tool_name == "delegate_booking":
        return await _delegate_booking(tool_input, db, user_id)
    return {"error": f"Unknown tool: {tool_name}"}


async def _delegate_booking(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    # Guard: must have explicit user confirmation
    if not tool_input.get("user_confirmed"):
        return {
            "status": "rejected",
            "error": "user_confirmed must be true. Only call delegate_booking after explicit user confirmation.",
        }

    # Guard: must have booking token
    booking_token = tool_input.get("booking_token", "")
    if not booking_token:
        return {
            "status": "rejected",
            "error": "booking_token is required. Obtain it from POST /api/v1/payments/confirm-booking.",
        }

    item_id = tool_input["item_id"]

    # Verify item ownership: item → itinerary → trip → user
    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary, ItineraryItem.itinerary_id == Itinerary.id)
        .join(Trip, Itinerary.trip_id == Trip.id)
        .where(ItineraryItem.id == item_id, Trip.user_id == user_id)
        .options(selectinload(Itinerary.items))
    )
    item = result.scalar_one_or_none()
    if not item:
        return {"status": "rejected", "error": "Item not found or access denied"}

    # Load trip to get trip_id
    itin_result = await db.execute(
        select(Itinerary).where(Itinerary.id == item.itinerary_id)
    )
    itinerary = itin_result.scalar_one_or_none()
    if not itinerary:
        return {"status": "rejected", "error": "Itinerary not found"}

    # Load user traveler details
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    travelers = user.travelers if user else []

    # Build booking context
    context = {
        "trip_id": itinerary.trip_id,
        "item_id": item_id,
        "user_id": user_id,
        "booking_type": tool_input.get("booking_type", "hotel"),
        "offer_id": tool_input.get("offer_id", ""),
        "offer_snapshot": tool_input.get("offer_snapshot", {}),
        "payment_method_id": user.default_payment_method_id if user else None,
        "booking_token": booking_token,
        "travelers": travelers,
    }

    # Delegate to booking sub-agent
    from app.agent.booking_agent import run_booking
    try:
        result_dict = await run_booking(context, db)
    except Exception as e:
        logger.exception("Booking sub-agent failed for item %d", item_id)
        return {"status": "failed", "error": str(e)}

    return result_dict
