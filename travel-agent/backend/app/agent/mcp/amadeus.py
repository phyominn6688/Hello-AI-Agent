"""Amadeus API MCP wrapper — flight and hotel search."""
import time
from typing import Any, Dict

import httpx

from app.config import settings

_token_cache: Dict[str, Any] = {}


async def _get_token() -> str:
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


def get_tools() -> list[dict]:
    return [
        {
            "name": "search_flights",
            "description": (
                "Search for available flights between two airports on a given date. "
                "Returns up to 10 flight options with prices, durations, and deep-links to book."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "IATA airport code (e.g. JFK)"},
                    "destination": {"type": "string", "description": "IATA airport code (e.g. PVG)"},
                    "departure_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "return_date": {
                        "type": "string",
                        "description": "Return date for round-trip (YYYY-MM-DD). Omit for one-way.",
                    },
                    "adults": {"type": "integer", "description": "Number of adult passengers", "default": 1},
                    "children": {"type": "integer", "description": "Number of child passengers (2-11)", "default": 0},
                    "cabin_class": {
                        "type": "string",
                        "enum": ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
                        "default": "ECONOMY",
                    },
                    "max_price": {"type": "number", "description": "Maximum price per person in USD"},
                },
                "required": ["origin", "destination", "departure_date", "adults"],
            },
        },
        {
            "name": "search_hotels",
            "description": (
                "Search for hotels in a city for given dates. Returns options with pricing, "
                "star rating, amenities, and deep-links to book."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "city_code": {"type": "string", "description": "IATA city code (e.g. SHA for Shanghai)"},
                    "check_in": {"type": "string", "description": "Check-in date YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "Check-out date YYYY-MM-DD"},
                    "adults": {"type": "integer", "default": 2},
                    "rooms": {"type": "integer", "default": 1},
                    "min_rating": {"type": "integer", "description": "Minimum star rating (1-5)", "default": 3},
                    "amenities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required amenities, e.g. ['SWIMMING_POOL', 'FAMILY_ROOMS']",
                    },
                },
                "required": ["city_code", "check_in", "check_out"],
            },
        },
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    if not settings.amadeus_client_id:
        return {"error": "Amadeus API not configured", "mock": True, "results": _mock_results(tool_name, tool_input)}

    token = await _get_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=settings.amadeus_base_url) as client:
        if tool_name == "search_flights":
            params = {
                "originLocationCode": tool_input["origin"],
                "destinationLocationCode": tool_input["destination"],
                "departureDate": tool_input["departure_date"],
                "adults": tool_input.get("adults", 1),
                "children": tool_input.get("children", 0),
                "travelClass": tool_input.get("cabin_class", "ECONOMY"),
                "max": 10,
                "currencyCode": "USD",
            }
            if "return_date" in tool_input:
                params["returnDate"] = tool_input["return_date"]
            if "max_price" in tool_input:
                params["maxPrice"] = tool_input["max_price"]

            resp = await client.get("/v2/shopping/flight-offers", params=params, headers=headers)
            resp.raise_for_status()
            raw = resp.json()
            return _format_flights(raw)

        elif tool_name == "search_hotels":
            params = {
                "cityCode": tool_input["city_code"],
                "checkInDate": tool_input["check_in"],
                "checkOutDate": tool_input["check_out"],
                "adults": tool_input.get("adults", 2),
                "roomQuantity": tool_input.get("rooms", 1),
                "ratings": str(tool_input.get("min_rating", 3)),
                "currency": "USD",
                "bestRateOnly": True,
            }
            resp = await client.get("/v3/shopping/hotel-offers", params=params, headers=headers)
            resp.raise_for_status()
            raw = resp.json()
            return _format_hotels(raw)

    return {"error": f"Unknown tool: {tool_name}"}


def _format_flights(raw: dict) -> dict:
    offers = []
    for offer in raw.get("data", [])[:10]:
        itineraries = offer.get("itineraries", [])
        price = offer.get("price", {})
        offers.append({
            "id": offer.get("id"),
            "price_usd": float(price.get("grandTotal", 0)),
            "currency": price.get("currency", "USD"),
            "itineraries": [
                {
                    "duration": itin.get("duration"),
                    "segments": [
                        {
                            "from": seg["departure"]["iataCode"],
                            "to": seg["arrival"]["iataCode"],
                            "departs": seg["departure"].get("at"),
                            "arrives": seg["arrival"].get("at"),
                            "carrier": seg.get("carrierCode"),
                            "flight_number": seg.get("number"),
                            "stops": seg.get("numberOfStops", 0),
                        }
                        for seg in itin.get("segments", [])
                    ],
                }
                for itin in itineraries
            ],
            "book_url": "https://www.amadeus.com",  # Deep-link placeholder
            "validating_carrier": offer.get("validatingAirlineCodes", [None])[0],
        })
    return {"flights": offers, "count": len(offers)}


def _format_hotels(raw: dict) -> dict:
    hotels = []
    for offer in raw.get("data", [])[:10]:
        hotel = offer.get("hotel", {})
        room_offers = offer.get("offers", [{}])
        best = room_offers[0] if room_offers else {}
        hotels.append({
            "hotel_id": hotel.get("hotelId"),
            "name": hotel.get("name"),
            "rating": hotel.get("rating"),
            "latitude": hotel.get("latitude"),
            "longitude": hotel.get("longitude"),
            "address": hotel.get("address", {}).get("lines", []),
            "price_per_night_usd": float(best.get("price", {}).get("total", 0)),
            "room_type": best.get("room", {}).get("typeEstimated", {}).get("category"),
            "check_in": best.get("checkInDate"),
            "check_out": best.get("checkOutDate"),
            "book_url": "https://www.amadeus.com",
        })
    return {"hotels": hotels, "count": len(hotels)}


def _mock_results(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "search_flights":
        return {
            "flights": [
                {
                    "id": "mock-1",
                    "price_usd": 850.00,
                    "currency": "USD",
                    "itineraries": [
                        {
                            "duration": "PT14H30M",
                            "segments": [
                                {
                                    "from": tool_input.get("origin", "JFK"),
                                    "to": tool_input.get("destination", "PVG"),
                                    "departs": f"{tool_input.get('departure_date', '2025-04-01')}T10:00:00",
                                    "arrives": f"{tool_input.get('departure_date', '2025-04-01')}T13:30:00+1",
                                    "carrier": "CA",
                                    "flight_number": "981",
                                    "stops": 0,
                                }
                            ],
                        }
                    ],
                    "book_url": "https://www.amadeus.com",
                    "validating_carrier": "CA",
                }
            ],
            "count": 1,
            "note": "Mock data — configure AMADEUS_CLIENT_ID for real results",
        }
    return {"hotels": [], "count": 0, "note": "Mock data"}
