"""Google Calendar MCP wrapper."""
import json
from typing import Any

from app.config import settings


def get_tools() -> list[dict]:
    return [
        {
            "name": "check_calendar_conflicts",
            "description": "Check the user's Google Calendar for conflicts during proposed travel dates.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "user_email": {"type": "string", "description": "User's Google account email"},
                },
                "required": ["start_date", "end_date", "user_email"],
            },
        },
        {
            "name": "update_calendar",
            "description": (
                "Add a confirmed booking or event to the user's Google Calendar. "
                "Call this after the user approves an itinerary item."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_email": {"type": "string"},
                    "title": {"type": "string", "description": "Event title (e.g. 'Flight JFK → PVG — CA981')"},
                    "start_datetime": {"type": "string", "description": "ISO 8601 datetime with timezone"},
                    "end_datetime": {"type": "string", "description": "ISO 8601 datetime with timezone"},
                    "location": {"type": "string", "description": "Location string"},
                    "description": {"type": "string", "description": "Details, booking ref, etc."},
                    "timezone": {"type": "string", "description": "IANA timezone (e.g. Asia/Shanghai)", "default": "UTC"},
                },
                "required": ["user_email", "title", "start_datetime", "end_datetime"],
            },
        },
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    if not settings.google_calendar_credentials_json:
        return _mock_result(tool_name, tool_input)

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_data = json.loads(settings.google_calendar_credentials_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_data,
            scopes=["https://www.googleapis.com/auth/calendar"],
        ).with_subject(tool_input.get("user_email", ""))

        service = build("calendar", "v3", credentials=creds)

        if tool_name == "check_calendar_conflicts":
            return await _check_conflicts(service, tool_input)
        elif tool_name == "update_calendar":
            return await _add_event(service, tool_input)

    except ImportError:
        return {"error": "google-api-python-client not installed", "mock": True, **_mock_result(tool_name, tool_input)}

    return {"error": f"Unknown tool: {tool_name}"}


async def _check_conflicts(service: Any, tool_input: dict) -> dict:
    events_result = service.events().list(
        calendarId="primary",
        timeMin=f"{tool_input['start_date']}T00:00:00Z",
        timeMax=f"{tool_input['end_date']}T23:59:59Z",
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    conflicts = [
        {
            "title": e.get("summary"),
            "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
        }
        for e in events
    ]
    return {
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts,
        "period": f"{tool_input['start_date']} to {tool_input['end_date']}",
    }


async def _add_event(service: Any, tool_input: dict) -> dict:
    event = {
        "summary": tool_input["title"],
        "location": tool_input.get("location", ""),
        "description": tool_input.get("description", ""),
        "start": {
            "dateTime": tool_input["start_datetime"],
            "timeZone": tool_input.get("timezone", "UTC"),
        },
        "end": {
            "dateTime": tool_input["end_datetime"],
            "timeZone": tool_input.get("timezone", "UTC"),
        },
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return {
        "success": True,
        "event_id": created.get("id"),
        "calendar_url": created.get("htmlLink"),
        "title": tool_input["title"],
    }


def _mock_result(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "check_calendar_conflicts":
        return {
            "has_conflicts": False,
            "conflicts": [],
            "period": f"{tool_input.get('start_date')} to {tool_input.get('end_date')}",
            "note": "Mock data — configure GOOGLE_CALENDAR_CREDENTIALS_JSON for real results",
        }
    return {
        "success": True,
        "event_id": "mock-event-id",
        "calendar_url": "https://calendar.google.com",
        "title": tool_input.get("title", ""),
        "note": "Mock data — configure GOOGLE_CALENDAR_CREDENTIALS_JSON for real results",
    }
