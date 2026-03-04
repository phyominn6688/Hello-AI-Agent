"""Ticketmaster + Eventbrite events MCP wrapper."""
import httpx

from app.config import settings


def get_tools() -> list[dict]:
    return [
        {
            "name": "search_events",
            "description": (
                "Search for events, concerts, shows, and attractions in a city during specified dates. "
                "Returns events with availability status and ticket purchase links."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "country_code": {"type": "string", "description": "ISO 3166-1 alpha-2 country code (e.g. CN, JP, US)"},
                    "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "keyword": {
                        "type": "string",
                        "description": "Optional keyword filter (e.g. 'acrobatics', 'opera', 'family')",
                    },
                    "classification": {
                        "type": "string",
                        "description": "Event type filter: music, sports, arts, family, film, etc.",
                    },
                    "family_friendly": {
                        "type": "boolean",
                        "description": "Filter for family-friendly events",
                        "default": False,
                    },
                },
                "required": ["city", "start_date", "end_date"],
            },
        }
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    if tool_name != "search_events":
        return {"error": f"Unknown tool: {tool_name}"}

    if not settings.ticketmaster_api_key:
        return _mock_events(tool_input)

    params = {
        "apikey": settings.ticketmaster_api_key,
        "city": tool_input["city"],
        "startDateTime": f"{tool_input['start_date']}T00:00:00Z",
        "endDateTime": f"{tool_input['end_date']}T23:59:59Z",
        "size": 10,
        "sort": "relevance,desc",
    }
    if cc := tool_input.get("country_code"):
        params["countryCode"] = cc
    if kw := tool_input.get("keyword"):
        params["keyword"] = kw
    if cls := tool_input.get("classification"):
        params["classificationName"] = cls
    if tool_input.get("family_friendly"):
        params["includeFamily"] = "yes"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    events = []
    for event in data.get("_embedded", {}).get("events", []):
        venue = event.get("_embedded", {}).get("venues", [{}])[0]
        dates = event.get("dates", {}).get("start", {})
        events.append({
            "id": event.get("id"),
            "name": event.get("name"),
            "date": dates.get("localDate"),
            "time": dates.get("localTime"),
            "venue": venue.get("name"),
            "address": venue.get("address", {}).get("line1"),
            "city": venue.get("city", {}).get("name"),
            "classification": event.get("classifications", [{}])[0].get("genre", {}).get("name"),
            "ticket_url": event.get("url"),
            "price_range": event.get("priceRanges", [{}])[0] if event.get("priceRanges") else None,
            "status": event.get("dates", {}).get("status", {}).get("code"),
            "image_url": next(
                (img["url"] for img in event.get("images", []) if img.get("ratio") == "16_9"),
                None,
            ),
        })

    return {"events": events, "count": len(events)}


def _mock_events(tool_input: dict) -> dict:
    return {
        "events": [
            {
                "id": "mock-event-1",
                "name": "Beijing National Acrobatics Show",
                "date": tool_input.get("start_date"),
                "time": "19:30:00",
                "venue": "Chaoyang Theater",
                "address": "36 East Third Ring Road North, Chaoyang",
                "city": tool_input["city"],
                "classification": "Arts & Theatre",
                "ticket_url": "https://www.ticketmaster.com",
                "price_range": {"min": 80, "max": 180, "currency": "USD"},
                "status": "onsale",
                "image_url": None,
            },
            {
                "id": "mock-event-2",
                "name": "Temple of Heaven Cultural Festival",
                "date": tool_input.get("start_date"),
                "time": "09:00:00",
                "venue": "Temple of Heaven",
                "address": "Tiantan East Rd, Dongcheng District",
                "city": tool_input["city"],
                "classification": "Family",
                "ticket_url": "https://www.ticketmaster.com",
                "price_range": {"min": 35, "max": 35, "currency": "CNY"},
                "status": "onsale",
                "image_url": None,
            },
        ],
        "count": 2,
        "note": "Mock data — configure TICKETMASTER_API_KEY for real results",
    }
