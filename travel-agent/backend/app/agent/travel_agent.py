"""Core travel agent — Claude claude-sonnet-4-6 with MCP-style tool use.

The agent operates in two modes:
- planning: trip planning, destination research, itinerary building
- guide: real-time assistance during the trip

Tool execution is dispatched to the appropriate MCP wrapper module.
"""
import json
import logging
from datetime import date, datetime, timezone
from typing import AsyncGenerator

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.mcp import (
    amadeus,
    calendar,
    opentable,
    ticketmaster,
    wallet,
    weather,
    tripdotcom,
)
from app.agent.prompts import GUIDE_SYSTEM_PROMPT, PLANNING_SYSTEM_PROMPT
from app.config import settings
from app.models.conversation import Conversation
from app.models.itinerary import Itinerary, ItineraryItem
from app.models.trip import Destination, Trip, TripStatus
from app.models.user import User

logger = logging.getLogger(__name__)

# ── Anthropic client singleton ─────────────────────────────────────────────────
# Created once at module load; raises immediately if key is missing.

if not settings.anthropic_api_key:
    raise RuntimeError(
        "ANTHROPIC_API_KEY is not set. Add it to your .env file or environment."
    )

_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ── Tool registry ──────────────────────────────────────────────────────────────

PLANNING_TOOLS = (
    amadeus.get_tools()
    + opentable.get_tools()
    + ticketmaster.get_tools()
    + weather.get_tools()
    + calendar.get_tools()
    + wallet.get_tools()
    + tripdotcom.get_tools()
)

# Guide mode adds real-time tools (Iteration 2: get_directions, get_wait_times, etc.)
GUIDE_TOOLS = PLANNING_TOOLS

TOOL_DISPATCH = {
    # Amadeus
    "search_flights": amadeus,
    "search_hotels": amadeus,
    # OpenTable / restaurants
    "search_restaurants": opentable,
    "check_availability": opentable,
    # Events
    "search_events": ticketmaster,
    # Weather
    "get_weather": weather,
    # Calendar
    "check_calendar_conflicts": calendar,
    "update_calendar": calendar,
    # Wallet / storage
    "save_to_wallet": wallet,
    "store_document": wallet,
    # Rail
    "search_rail": tripdotcom,
}


# ── Agent ──────────────────────────────────────────────────────────────────────


async def _load_or_create_conversation(trip_id: int, db: AsyncSession) -> Conversation:
    result = await db.execute(
        select(Conversation).where(Conversation.trip_id == trip_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        conv = Conversation(trip_id=trip_id, messages=[])
        db.add(conv)
        await db.flush()
    return conv


async def _build_system_prompt(trip: Trip, db: AsyncSession) -> str:
    today = date.today().isoformat()
    mode = trip.status

    result = await db.execute(select(User).where(User.id == trip.user_id))
    user = result.scalar_one_or_none()
    traveler_profile = ""
    if user:
        travelers = user.travelers or []
        prefs = user.preferences or {}
        # Include age context so the agent can make age-gated decisions
        age_context = ""
        if user.date_of_birth:
            today_date = date.today()
            age = (
                today_date.year
                - user.date_of_birth.year
                - (
                    (today_date.month, today_date.day)
                    < (user.date_of_birth.month, user.date_of_birth.day)
                )
            )
            age_context = f" Age: {age} (verification: {user.age_declaration_method or 'none'})."
        traveler_profile = (
            f"Travelers: {json.dumps(travelers)}. Preferences: {json.dumps(prefs)}.{age_context}"
        )

    destinations = [
        f"{d.city}, {d.country} ({d.arrival_date} – {d.departure_date})"
        for d in trip.destinations
    ]
    travel_dates = (
        f"{trip.start_date} to {trip.end_date}"
        if trip.start_date and trip.end_date
        else "Not yet set"
    )
    budget = (
        f"{trip.budget_per_person} {trip.currency} per person"
        if trip.budget_per_person
        else "Not specified"
    )

    if mode == TripStatus.active:
        result = await db.execute(
            select(Itinerary)
            .options(selectinload(Itinerary.items))
            .where(Itinerary.trip_id == trip.id, Itinerary.date == today)
        )
        todays_itin = result.scalar_one_or_none()
        items_summary = "No items scheduled yet."
        if todays_itin and todays_itin.items:
            items_summary = "\n".join(
                f"- {item.start_time or '?'} {item.name} ({item.flexibility})"
                for item in sorted(todays_itin.items, key=lambda x: x.start_time or "")
            )
        return GUIDE_SYSTEM_PROMPT.format(
            trip_id=trip.id,
            today=today,
            current_location=destinations[0] if destinations else "Unknown",
            todays_itinerary=items_summary,
            next_fixed_event="None",
            weather_summary="(use get_weather tool for current conditions)",
        )
    else:
        return PLANNING_SYSTEM_PROMPT.format(
            trip_id=trip.id,
            traveler_profile=traveler_profile,
            destinations=", ".join(destinations) if destinations else "Not yet selected",
            travel_dates=travel_dates,
            budget=budget,
        )


async def chat_stream(
    trip_id: int,
    user_message: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Stream agent response as SSE events.

    Yields strings in SSE format:
        data: {"type": "text", "content": "..."}\n\n
        data: {"type": "tool_use", "tool": "...", "input": {...}}\n\n
        data: {"type": "tool_result", "tool": "...", "result": {...}}\n\n
        data: {"type": "done"}\n\n
    """
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.destinations))
        .where(Trip.id == trip_id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        yield _sse({"type": "error", "message": "Trip not found"})
        return

    conv = await _load_or_create_conversation(trip_id, db)
    system_prompt = await _build_system_prompt(trip, db)
    tools = GUIDE_TOOLS if trip.status == TripStatus.active else PLANNING_TOOLS

    now_iso = datetime.now(timezone.utc).isoformat()

    # Build full message list including the new user message.
    # conv.messages stores the complete exchange (user turns, assistant turns,
    # tool-result turns) so history is faithfully replayed to the API.
    messages = list(conv.messages)
    new_user_msg = {"role": "user", "content": user_message, "timestamp": now_iso}
    messages.append(new_user_msg)

    # api_messages strips timestamps — Anthropic API only accepts role + content
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    full_assistant_text = ""
    iteration = 0

    # Agentic loop — handles multi-step tool calls
    while True:
        if iteration >= settings.agent_max_iterations:
            logger.warning(
                "Agent reached max iterations (%d) for trip %d",
                settings.agent_max_iterations,
                trip_id,
            )
            yield _sse({
                "type": "error",
                "message": "The agent reached its maximum processing steps. Please try rephrasing your request.",
            })
            break

        iteration += 1

        response = _anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=api_messages,
            stream=True,
        )

        current_tool_use_block: dict | None = None
        current_tool_input_json = ""
        response_content_blocks = []

        with response as stream:
            for event in stream:
                etype = event.type

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        response_content_blocks.append({"type": "text", "text": ""})
                    elif block.type == "tool_use":
                        current_tool_use_block = {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": {},
                        }
                        current_tool_input_json = ""
                        yield _sse({"type": "tool_use", "tool": block.name, "id": block.id})

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        text = delta.text
                        full_assistant_text += text
                        if response_content_blocks and response_content_blocks[-1]["type"] == "text":
                            response_content_blocks[-1]["text"] += text
                        yield _sse({"type": "text", "content": text})

                    elif delta.type == "input_json_delta":
                        current_tool_input_json += delta.partial_json

                elif etype == "content_block_stop":
                    if current_tool_use_block is not None:
                        try:
                            current_tool_use_block["input"] = json.loads(current_tool_input_json)
                        except json.JSONDecodeError:
                            current_tool_use_block["input"] = {}
                        response_content_blocks.append(current_tool_use_block)
                        current_tool_use_block = None
                        current_tool_input_json = ""

        # Append assistant turn to api_messages and to the persistent store
        assistant_ts = datetime.now(timezone.utc).isoformat()
        api_messages.append({"role": "assistant", "content": response_content_blocks})
        messages.append({
            "role": "assistant",
            "content": response_content_blocks,
            "timestamp": assistant_ts,
        })

        tool_use_blocks = [b for b in response_content_blocks if b.get("type") == "tool_use"]

        if not tool_use_blocks:
            break

        # Execute all tools and build tool_results message
        tool_results = []
        for tool_block in tool_use_blocks:
            tool_name = tool_block["name"]
            tool_input = tool_block["input"]
            tool_id = tool_block["id"]

            module = TOOL_DISPATCH.get(tool_name)
            if module:
                try:
                    result_data = await module.execute_tool(tool_name, tool_input)
                except Exception as e:
                    logger.exception("Tool %s failed", tool_name)
                    result_data = {"error": str(e)}
            else:
                result_data = {"error": f"Tool '{tool_name}' not implemented"}

            yield _sse({"type": "tool_result", "tool": tool_name, "result": result_data})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps(result_data),
            })

        # Append tool-result turn — persisted so the next request replays correctly
        tool_result_ts = datetime.now(timezone.utc).isoformat()
        api_messages.append({"role": "user", "content": tool_results})
        messages.append({
            "role": "user",
            "content": tool_results,
            "timestamp": tool_result_ts,
        })

    # Persist the full updated exchange (including tool turns)
    conv.messages = messages
    await db.flush()

    yield _sse({"type": "done"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
