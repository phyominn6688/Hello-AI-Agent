"""Trip.com high-speed rail search MCP wrapper.

Trip.com provides rail search for China, Japan, and other Asian rail networks.
Requires Trip.com affiliate/partner API access.
"""
import httpx

from app.config import settings


def get_tools() -> list[dict]:
    return [
        {
            "name": "search_rail",
            "description": (
                "Search for high-speed rail and train options between two cities. "
                "Best for China (CRH/bullet trains), Japan (Shinkansen), and other Asian networks. "
                "Returns train options with departure times, duration, seat classes, and booking links."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin_city": {"type": "string", "description": "Departure city name (e.g. 'Beijing')"},
                    "destination_city": {"type": "string", "description": "Arrival city name (e.g. 'Shanghai')"},
                    "departure_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "passengers": {"type": "integer", "default": 1},
                    "seat_class": {
                        "type": "string",
                        "enum": ["economy", "first", "business"],
                        "default": "economy",
                    },
                },
                "required": ["origin_city", "destination_city", "departure_date"],
            },
        }
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    if tool_name != "search_rail":
        return {"error": f"Unknown tool: {tool_name}"}

    if not settings.tripdotcom_api_key:
        return _mock_rail(tool_input)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://us.trip.com/api/train/search",
            params={
                "fromCity": tool_input["origin_city"],
                "toCity": tool_input["destination_city"],
                "departDate": tool_input["departure_date"],
                "seatType": tool_input.get("seat_class", "economy"),
                "adultNum": tool_input.get("passengers", 1),
            },
            headers={"Authorization": f"Bearer {settings.tripdotcom_api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return _format_rail(resp.json(), tool_input)


def _format_rail(data: dict, tool_input: dict) -> dict:
    trains = []
    for item in data.get("trainList", [])[:8]:
        trains.append({
            "train_number": item.get("trainNumber"),
            "type": item.get("trainType"),  # G=high-speed, D=intercity, K=regular
            "origin": item.get("fromStation"),
            "destination": item.get("toStation"),
            "departs": item.get("departTime"),
            "arrives": item.get("arriveTime"),
            "duration": item.get("duration"),
            "date": tool_input["departure_date"],
            "seat_options": [
                {
                    "class": seat.get("seatType"),
                    "price_cny": seat.get("price"),
                    "available": seat.get("available", True),
                }
                for seat in item.get("seats", [])
            ],
            "book_url": item.get("bookUrl", "https://www.trip.com/trains/"),
        })
    return {"trains": trains, "count": len(trains)}


def _mock_rail(tool_input: dict) -> dict:
    return {
        "trains": [
            {
                "train_number": "G1",
                "type": "G",
                "origin": tool_input["origin_city"],
                "destination": tool_input["destination_city"],
                "departs": "07:00",
                "arrives": "12:28",
                "duration": "5h28m",
                "date": tool_input["departure_date"],
                "seat_options": [
                    {"class": "Second Class", "price_cny": 553, "available": True},
                    {"class": "First Class", "price_cny": 935, "available": True},
                    {"class": "Business Class", "price_cny": 1748, "available": True},
                ],
                "book_url": "https://www.trip.com/trains/",
            },
            {
                "train_number": "G3",
                "type": "G",
                "origin": tool_input["origin_city"],
                "destination": tool_input["destination_city"],
                "departs": "09:00",
                "arrives": "14:28",
                "duration": "5h28m",
                "date": tool_input["departure_date"],
                "seat_options": [
                    {"class": "Second Class", "price_cny": 553, "available": True},
                    {"class": "First Class", "price_cny": 935, "available": False},
                    {"class": "Business Class", "price_cny": 1748, "available": True},
                ],
                "book_url": "https://www.trip.com/trains/",
            },
        ],
        "count": 2,
        "note": "Mock data — configure TRIPDOTCOM_API_KEY for real results",
    }
