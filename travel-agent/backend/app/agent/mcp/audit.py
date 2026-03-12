"""Audit MCP wrapper — log booking actions to AgentAction table.

Used exclusively by the booking sub-agent to create an immutable audit trail
of every write operation attempted during a booking session.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.itinerary import AgentAction

logger = logging.getLogger(__name__)


def get_tools() -> list[dict]:
    return [
        {
            "name": "log_booking_action",
            "description": (
                "Write an audit log entry for a booking action. "
                "MUST be called before and after every write operation."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "trip_id": {"type": "integer"},
                    "item_id": {"type": "integer", "description": "ItineraryItem ID (optional)"},
                    "agent_type": {
                        "type": "string",
                        "description": "Which agent is performing the action",
                        "default": "booking",
                    },
                    "tool_name": {"type": "string", "description": "Name of the tool being called"},
                    "action_type": {
                        "type": "string",
                        "description": "Human-readable action descriptor (e.g. 'book_hotel', 'verify_token')",
                    },
                    "reason": {"type": "string", "description": "Why this action is being taken"},
                    "input_snapshot": {
                        "type": "object",
                        "description": "Sanitized copy of the tool input (omit PII if possible)",
                    },
                    "output_snapshot": {
                        "type": "object",
                        "description": "Sanitized copy of the tool output",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["success", "failed", "pending", "skipped"],
                        "default": "success",
                    },
                    "booking_token_hash": {
                        "type": "string",
                        "description": "SHA-256 hash of the booking token used (never the raw token)",
                    },
                    "duration_ms": {"type": "integer", "description": "How long the operation took in ms"},
                },
                "required": ["trip_id", "action_type", "reason"],
            },
        }
    ]


async def execute_tool(tool_name: str, tool_input: dict, db: AsyncSession, user_id: int) -> dict:
    if tool_name == "log_booking_action":
        return await _log_booking_action(tool_input, db)
    return {"error": f"Unknown tool: {tool_name}"}


async def _log_booking_action(tool_input: dict, db: AsyncSession) -> dict:
    action = AgentAction(
        trip_id=tool_input["trip_id"],
        item_id=tool_input.get("item_id"),
        action_type=tool_input.get("action_type", "unknown"),
        reason=tool_input.get("reason", ""),
        agent_type=tool_input.get("agent_type", "booking"),
        tool_name=tool_input.get("tool_name"),
        input_snapshot=tool_input.get("input_snapshot"),
        output_snapshot=tool_input.get("output_snapshot"),
        status=tool_input.get("status", "success"),
        booking_token_hash=tool_input.get("booking_token_hash"),
        duration_ms=tool_input.get("duration_ms"),
    )
    db.add(action)
    await db.flush()
    logger.info(
        "Audit log: trip=%d item=%s action=%s status=%s",
        action.trip_id,
        action.item_id,
        action.action_type,
        action.status,
    )
    return {"logged": True, "action_id": action.id}
