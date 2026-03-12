"""Wishlist MCP wrapper — save and retrieve deferred itinerary options.

Allows the agent to save interesting options when the schedule is full or the
user is undecided, and later promote them to scheduled items.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.itinerary import Itinerary, ItineraryItem, ItemType, WishlistStatus, Flexibility
from app.models.trip import Trip

logger = logging.getLogger(__name__)


def get_tools() -> list[dict]:
    return [
        {
            "name": "add_to_wishlist",
            "description": (
                "Save an interesting option to the trip wishlist for later consideration. "
                "Use when the schedule is full, the user is undecided, or they say "
                "'save that', 'keep that in mind', 'maybe later', or 'good to know'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "trip_id": {"type": "integer", "description": "Trip DB ID"},
                    "name": {"type": "string", "description": "Name of the place or activity"},
                    "type": {
                        "type": "string",
                        "enum": ["restaurant", "activity", "event", "hotel"],
                        "description": "Type of wishlist item",
                    },
                    "city": {"type": "string", "description": "City where the item is located"},
                    "country": {"type": "string", "description": "Country where the item is located"},
                    "notes": {"type": "string", "description": "Why this was saved, any important details"},
                    "estimated_duration_mins": {
                        "type": "integer",
                        "description": "Estimated time needed in minutes",
                    },
                },
                "required": ["trip_id", "name", "type", "city"],
            },
        },
        {
            "name": "get_wishlist",
            "description": (
                "Retrieve wishlist items for a trip. "
                "Use when looking for backup options or when free time opens up."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "trip_id": {"type": "integer", "description": "Trip DB ID"},
                    "type": {
                        "type": "string",
                        "enum": ["restaurant", "activity", "event", "hotel"],
                        "description": "Filter by item type (optional)",
                    },
                    "city": {
                        "type": "string",
                        "description": "Filter by city (optional)",
                    },
                },
                "required": ["trip_id"],
            },
        },
    ]


async def execute_tool(tool_name: str, tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    if tool_name == "add_to_wishlist":
        return await _add_to_wishlist(tool_input, db, user_id)
    elif tool_name == "get_wishlist":
        return await _get_wishlist(tool_input, db, user_id)
    return {"error": f"Unknown tool: {tool_name}"}


async def _add_to_wishlist(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    trip_id = tool_input["trip_id"]

    # Verify trip ownership
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        return {"error": "Trip not found"}

    # Wishlist items use a sentinel date (today) and no itinerary date constraint;
    # we need a date to create the Itinerary row — use a special "wishlist" sentinel
    # by looking for or creating a wishlist-only itinerary with date=9999-12-31.
    from datetime import date as date_type
    wishlist_date = date_type(9999, 12, 31)

    result = await db.execute(
        select(Itinerary).where(
            Itinerary.trip_id == trip_id,
            Itinerary.date == wishlist_date,
        )
    )
    itin = result.scalar_one_or_none()
    if not itin:
        itin = Itinerary(trip_id=trip_id, date=wishlist_date)
        db.add(itin)
        await db.flush()

    # Map type string to ItemType enum
    type_map = {
        "restaurant": ItemType.restaurant,
        "activity": ItemType.activity,
        "event": ItemType.event,
        "hotel": ItemType.hotel,
    }
    item_type = type_map.get(tool_input["type"], ItemType.activity)

    item_data: dict = {
        "city": tool_input.get("city", ""),
        "country": tool_input.get("country", ""),
        "notes": tool_input.get("notes", ""),
    }

    item = ItineraryItem(
        itinerary_id=itin.id,
        type=item_type,
        flexibility=Flexibility.flexible,
        name=tool_input["name"],
        duration_mins=tool_input.get("estimated_duration_mins"),
        wishlist_status=WishlistStatus.wishlist,
        item_data=item_data,
    )
    db.add(item)
    await db.flush()

    logger.info("Added wishlist item %d for trip %d", item.id, trip_id)
    return {
        "status": "saved",
        "item_id": item.id,
        "message": f"'{tool_input['name']}' saved to wishlist.",
    }


async def _get_wishlist(tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    trip_id = tool_input["trip_id"]

    # Verify trip ownership
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        return {"error": "Trip not found"}

    from datetime import date as date_type
    wishlist_date = date_type(9999, 12, 31)

    result = await db.execute(
        select(Itinerary)
        .options(selectinload(Itinerary.items))
        .where(Itinerary.trip_id == trip_id, Itinerary.date == wishlist_date)
    )
    itin = result.scalar_one_or_none()
    if not itin:
        return {"items": [], "count": 0}

    items = [
        i for i in itin.items
        if i.wishlist_status == WishlistStatus.wishlist
    ]

    # Optional filters
    if filter_type := tool_input.get("type"):
        type_map = {
            "restaurant": ItemType.restaurant,
            "activity": ItemType.activity,
            "event": ItemType.event,
            "hotel": ItemType.hotel,
        }
        mapped = type_map.get(filter_type)
        if mapped:
            items = [i for i in items if i.type == mapped]

    if filter_city := tool_input.get("city"):
        items = [
            i for i in items
            if filter_city.lower() in (i.item_data or {}).get("city", "").lower()
        ]

    return {
        "items": [
            {
                "id": i.id,
                "name": i.name,
                "type": i.type.value,
                "city": (i.item_data or {}).get("city", ""),
                "country": (i.item_data or {}).get("country", ""),
                "notes": (i.item_data or {}).get("notes", ""),
                "estimated_duration_mins": i.duration_mins,
                "wishlist_status": i.wishlist_status.value,
            }
            for i in items
        ],
        "count": len(items),
    }
