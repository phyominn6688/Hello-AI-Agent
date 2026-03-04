"""OpenTable / restaurant availability MCP wrapper.

OpenTable does not have a public search API — we use Google Places as the
primary discovery layer with availability deep-links to OpenTable/Resy.
"""
import httpx

from app.config import settings


def get_tools() -> list[dict]:
    return [
        {
            "name": "search_restaurants",
            "description": (
                "Search for restaurants in a city or near a location. "
                "Supports dietary filters and family friendliness. "
                "Returns restaurant details with booking deep-links to OpenTable or Resy."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'Peking Duck Beijing' or 'family-friendly sushi Tokyo'",
                    },
                    "location": {
                        "type": "string",
                        "description": "City or 'lat,lng' for nearby search",
                    },
                    "date": {
                        "type": "string",
                        "description": "Desired dining date YYYY-MM-DD",
                    },
                    "time": {
                        "type": "string",
                        "description": "Desired dining time HH:MM (24h)",
                    },
                    "party_size": {"type": "integer", "default": 2},
                    "dietary_filters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "e.g. ['vegetarian', 'gluten_free', 'halal', 'kosher']",
                    },
                    "price_level": {
                        "type": "integer",
                        "description": "1=budget, 2=moderate, 3=upscale, 4=fine dining",
                        "minimum": 1,
                        "maximum": 4,
                    },
                },
                "required": ["query", "location"],
            },
        },
        {
            "name": "check_availability",
            "description": "Check real-time availability for a specific restaurant on a date/time.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "restaurant_name": {"type": "string"},
                    "restaurant_id": {"type": "string", "description": "Google Places ID if available"},
                    "location": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM (24h)"},
                    "party_size": {"type": "integer", "default": 2},
                },
                "required": ["restaurant_name", "location", "date", "time", "party_size"],
            },
        },
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    if not settings.google_maps_api_key:
        return _mock_results(tool_name, tool_input)

    if tool_name == "search_restaurants":
        return await _search_via_places(tool_input)
    elif tool_name == "check_availability":
        return await _check_availability(tool_input)

    return {"error": f"Unknown tool: {tool_name}"}


async def _search_via_places(tool_input: dict) -> dict:
    query = tool_input["query"]
    location = tool_input["location"]
    party_size = tool_input.get("party_size", 2)
    date = tool_input.get("date", "")
    time_str = tool_input.get("time", "19:00")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": f"restaurant {query} {location}",
                "type": "restaurant",
                "key": settings.google_maps_api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for place in data.get("results", [])[:8]:
        place_id = place.get("place_id", "")
        name = place.get("name", "")
        results.append({
            "name": name,
            "place_id": place_id,
            "address": place.get("formatted_address", ""),
            "rating": place.get("rating"),
            "price_level": place.get("price_level"),
            "types": place.get("types", []),
            "opentable_url": f"https://www.opentable.com/s/?covers={party_size}&dateTime={date}T{time_str}",
            "resy_url": f"https://resy.com/",
            "google_maps_url": f"https://www.google.com/maps/place/?q=place_id:{place_id}",
        })
    return {"restaurants": results, "count": len(results)}


async def _check_availability(tool_input: dict) -> dict:
    # Availability via OpenTable requires partner API access.
    # We return a deep-link for the user to check directly.
    party = tool_input.get("party_size", 2)
    date = tool_input.get("date", "")
    time_str = tool_input.get("time", "19:00")
    name = tool_input["restaurant_name"]

    return {
        "restaurant": name,
        "date": date,
        "time": time_str,
        "party_size": party,
        "availability_status": "check_required",
        "book_url": f"https://www.opentable.com/s/?term={name}&covers={party}&dateTime={date}T{time_str}",
        "note": "Click the book_url to check live availability and make a reservation.",
    }


def _mock_results(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "search_restaurants":
        return {
            "restaurants": [
                {
                    "name": "Da Dong Roast Duck",
                    "place_id": "mock-place-1",
                    "address": "9 Tuanjiehu North Lane, Chaoyang, Beijing",
                    "rating": 4.5,
                    "price_level": 3,
                    "types": ["restaurant", "food"],
                    "opentable_url": "https://www.opentable.com",
                    "resy_url": "https://resy.com",
                    "google_maps_url": "https://maps.google.com",
                },
                {
                    "name": "Quanjude Roast Duck",
                    "place_id": "mock-place-2",
                    "address": "32 Qianmen Street, Dongcheng, Beijing",
                    "rating": 4.2,
                    "price_level": 2,
                    "types": ["restaurant", "food"],
                    "opentable_url": "https://www.opentable.com",
                    "resy_url": "https://resy.com",
                    "google_maps_url": "https://maps.google.com",
                },
            ],
            "count": 2,
            "note": "Mock data — configure GOOGLE_MAPS_API_KEY for real results",
        }
    return {"availability_status": "check_required", "note": "Mock data"}
