"""OpenWeatherMap MCP wrapper."""
import httpx

from app.config import settings


def get_tools() -> list[dict]:
    return [
        {
            "name": "get_weather",
            "description": (
                "Get current weather and 5-day forecast for a city. "
                "Includes temperature, conditions, precipitation, wind, and UV index."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name (e.g. 'Beijing')"},
                    "country_code": {
                        "type": "string",
                        "description": "ISO-3166 2-letter country code (e.g. CN). Optional but improves accuracy.",
                    },
                    "units": {
                        "type": "string",
                        "enum": ["metric", "imperial"],
                        "default": "metric",
                        "description": "Temperature units: metric=°C, imperial=°F",
                    },
                },
                "required": ["city"],
            },
        }
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    if tool_name != "get_weather":
        return {"error": f"Unknown tool: {tool_name}"}

    if not settings.openweather_api_key:
        return _mock_weather(tool_input)

    location = tool_input["city"]
    if cc := tool_input.get("country_code"):
        location = f"{location},{cc}"

    units = tool_input.get("units", "metric")

    async with httpx.AsyncClient() as client:
        current_resp = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": location, "appid": settings.openweather_api_key, "units": units},
        )
        forecast_resp = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": location,
                "appid": settings.openweather_api_key,
                "units": units,
                "cnt": 40,
            },
        )

    current_resp.raise_for_status()
    forecast_resp.raise_for_status()

    current = current_resp.json()
    forecast = forecast_resp.json()
    unit_sym = "°C" if units == "metric" else "°F"

    daily: dict[str, list] = {}
    for item in forecast.get("list", []):
        day = item["dt_txt"][:10]
        daily.setdefault(day, []).append(item)

    days = []
    for day, readings in sorted(daily.items())[:5]:
        temps = [r["main"]["temp"] for r in readings]
        descriptions = [r["weather"][0]["description"] for r in readings]
        days.append({
            "date": day,
            "min_temp": f"{min(temps):.1f}{unit_sym}",
            "max_temp": f"{max(temps):.1f}{unit_sym}",
            "description": descriptions[len(descriptions) // 2],
            "precipitation_mm": sum(r.get("rain", {}).get("3h", 0) for r in readings),
        })

    return {
        "city": current.get("name"),
        "current": {
            "temp": f"{current['main']['temp']:.1f}{unit_sym}",
            "feels_like": f"{current['main']['feels_like']:.1f}{unit_sym}",
            "description": current["weather"][0]["description"],
            "humidity": f"{current['main']['humidity']}%",
            "wind_kmh": f"{current['wind']['speed'] * 3.6:.1f} km/h" if units == "metric" else f"{current['wind']['speed']:.1f} mph",
            "visibility_km": current.get("visibility", 0) / 1000,
        },
        "forecast": days,
    }


def _mock_weather(tool_input: dict) -> dict:
    return {
        "city": tool_input["city"],
        "current": {
            "temp": "12°C",
            "feels_like": "10°C",
            "description": "partly cloudy",
            "humidity": "65%",
            "wind_kmh": "15.0 km/h",
            "visibility_km": 10.0,
        },
        "forecast": [
            {"date": "2025-04-01", "min_temp": "8°C", "max_temp": "15°C", "description": "sunny", "precipitation_mm": 0},
            {"date": "2025-04-02", "min_temp": "10°C", "max_temp": "17°C", "description": "partly cloudy", "precipitation_mm": 0},
            {"date": "2025-04-03", "min_temp": "9°C", "max_temp": "14°C", "description": "light rain", "precipitation_mm": 4.2},
            {"date": "2025-04-04", "min_temp": "7°C", "max_temp": "13°C", "description": "cloudy", "precipitation_mm": 0.5},
            {"date": "2025-04-05", "min_temp": "11°C", "max_temp": "18°C", "description": "sunny", "precipitation_mm": 0},
        ],
        "note": "Mock data — configure OPENWEATHER_API_KEY for real results",
    }
