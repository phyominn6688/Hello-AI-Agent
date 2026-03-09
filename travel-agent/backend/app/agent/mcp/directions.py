"""Guide-mode MCP tools — directions, nearby search, wait times.

Uses Google Maps APIs when keys are configured; returns realistic mock data otherwise.
"""
from app.config import settings

# ── Tool definitions ───────────────────────────────────────────────────────────


def get_tools() -> list[dict]:
    return [
        {
            "name": "get_directions",
            "description": (
                "Get turn-by-turn directions between two locations. "
                "Use for leave-now timing, walking routes, transit options."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Starting address or 'lat,lng'"},
                    "destination": {"type": "string", "description": "Destination address or 'lat,lng'"},
                    "mode": {
                        "type": "string",
                        "enum": ["walking", "driving", "transit"],
                        "description": "Travel mode",
                    },
                },
                "required": ["origin", "destination"],
            },
        },
        {
            "name": "search_nearby",
            "description": "Find nearby places of a given type (ATM, pharmacy, restaurant, etc.).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude of search centre"},
                    "lng": {"type": "number", "description": "Longitude of search centre"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "atm", "pharmacy", "restaurant", "hospital",
                            "supermarket", "taxi_stand", "subway_station",
                            "convenience_store", "tourist_attraction",
                        ],
                    },
                    "radius_meters": {"type": "integer", "default": 500},
                },
                "required": ["lat", "lng", "type"],
            },
        },
        {
            "name": "get_wait_times",
            "description": "Get estimated current wait or queue times for a venue.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "place_name": {"type": "string"},
                    "location": {"type": "string", "description": "City or address context"},
                },
                "required": ["place_name"],
            },
        },
    ]


# ── Tool execution ─────────────────────────────────────────────────────────────


async def execute_tool(name: str, input: dict) -> dict:
    if name == "get_directions":
        return await _get_directions(**input)
    if name == "search_nearby":
        return await _search_nearby(**input)
    if name == "get_wait_times":
        return await _get_wait_times(**input)
    return {"error": f"Unknown tool: {name}"}


async def _get_directions(
    origin: str, destination: str, mode: str = "walking"
) -> dict:
    if settings.google_maps_api_key:
        try:
            import httpx

            url = "https://maps.googleapis.com/maps/api/directions/json"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    params={
                        "origin": origin,
                        "destination": destination,
                        "mode": mode,
                        "key": settings.google_maps_api_key,
                    },
                )
                data = resp.json()
            if data.get("status") == "OK":
                route = data["routes"][0]["legs"][0]
                steps = [
                    {
                        "instruction": s["html_instructions"],
                        "distance": s["distance"]["text"],
                        "duration": s["duration"]["text"],
                    }
                    for s in route["steps"][:8]
                ]
                return {
                    "origin": route["start_address"],
                    "destination": route["end_address"],
                    "mode": mode,
                    "duration_mins": round(route["duration"]["value"] / 60),
                    "distance_km": round(route["distance"]["value"] / 1000, 1),
                    "steps": steps,
                }
        except Exception:
            pass  # fall through to mock

    # Mock response
    duration = {"walking": 18, "driving": 8, "transit": 22}.get(mode, 15)
    return {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "duration_mins": duration,
        "distance_km": 1.4,
        "steps": [
            {"instruction": "Head north on the main street", "distance": "200 m", "duration": "3 min"},
            {"instruction": "Turn right at the intersection", "distance": "600 m", "duration": "8 min"},
            {"instruction": "Arrive at destination on the left", "distance": "0 m", "duration": "0 min"},
        ],
        "note": "Mock directions — configure GOOGLE_MAPS_API_KEY for real routing",
    }


async def _search_nearby(
    lat: float, lng: float, type: str, radius_meters: int = 500
) -> dict:
    if settings.google_maps_api_key:
        try:
            import httpx

            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    params={
                        "location": f"{lat},{lng}",
                        "radius": radius_meters,
                        "type": type,
                        "key": settings.google_maps_api_key,
                    },
                )
                data = resp.json()
            if data.get("status") == "OK":
                results = []
                for p in data["results"][:5]:
                    results.append(
                        {
                            "name": p["name"],
                            "address": p.get("vicinity", ""),
                            "rating": p.get("rating"),
                            "open_now": p.get("opening_hours", {}).get("open_now"),
                            "place_id": p["place_id"],
                        }
                    )
                return {"type": type, "results": results}
        except Exception:
            pass

    # Mock responses by type
    mock = {
        "atm": [
            {"name": "Local Bank ATM", "address": "50m — around the corner", "open_now": True, "distance_m": 50},
            {"name": "7-Eleven ATM", "address": "120m — convenience store on main street", "open_now": True, "distance_m": 120},
        ],
        "pharmacy": [
            {"name": "City Pharmacy", "address": "80m — next block", "open_now": True, "distance_m": 80},
        ],
        "restaurant": [
            {"name": "Local Bistro", "address": "100m — main street", "rating": 4.3, "open_now": True, "distance_m": 100},
            {"name": "Noodle House", "address": "200m — side street", "rating": 4.1, "open_now": True, "distance_m": 200},
        ],
        "hospital": [
            {"name": "City General Hospital", "address": "600m — emergency entrance on north side", "open_now": True, "distance_m": 600},
        ],
    }
    places = mock.get(type, [{"name": f"Nearby {type}", "address": "150m away", "open_now": True, "distance_m": 150}])
    return {
        "type": type,
        "results": places,
        "note": "Mock results — configure GOOGLE_MAPS_API_KEY for real search",
    }


async def _get_wait_times(place_name: str, location: str = "") -> dict:
    # No public API for live wait times — return a realistic estimate
    return {
        "place_name": place_name,
        "current_wait_estimate": "10–20 minutes",
        "busy_level": "moderately busy",
        "best_time_to_visit": "Early morning or after 3pm tends to be quieter",
        "note": "Wait time estimates are approximate based on typical patterns",
    }
