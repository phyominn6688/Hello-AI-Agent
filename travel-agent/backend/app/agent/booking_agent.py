"""Ephemeral booking sub-agent.

Called by the main travel agent via delegate_booking. Runs its own short
Claude conversation (not persisted to the Conversation table). Max 5 iterations.

The sub-agent has access only to write-enabled tools:
  - amadeus_booking (book_hotel)
  - reservation_booking (confirm_restaurant_booking)
  - audit (log_booking_action)
"""
import json
import logging
import time

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

BOOKING_SYSTEM_PROMPT = """\
You are a booking execution agent. Your sole job is to complete a specific booking \
transaction that the user has already confirmed.

Rules:
- You MUST call log_booking_action before and after every write operation
- You MUST verify the booking_token is present in the context before any write
- You MUST check for existing booking_ref on the item before booking (idempotency)
- You MUST return a final JSON response:
  {"status": "confirmed"|"failed"|"requires_user_action", "booking_ref": "...", "details": {}, "error": "..."}
- You have NO search tools — work only with the offer data provided in context
- If a price change is detected, return status="requires_user_action" with the new price — do NOT book
- Never book without a valid booking_token
- Keep your responses concise — you are executing, not conversing
"""

# Max iterations to prevent runaway loops
_MAX_ITERATIONS = 5

# Tools available to the booking sub-agent
_BOOKING_TOOLS: list[dict] = []

def _get_booking_tools() -> list[dict]:
    """Lazy-load tools to avoid circular imports."""
    global _BOOKING_TOOLS
    if not _BOOKING_TOOLS:
        from app.agent.mcp import amadeus_booking, reservation_booking, audit
        _BOOKING_TOOLS = (
            amadeus_booking.get_tools()
            + reservation_booking.get_tools()
            + audit.get_tools()
        )
    return _BOOKING_TOOLS


_TOOL_DISPATCH_BOOKING = {
    "book_hotel": "amadeus_booking",
    "confirm_restaurant_booking": "reservation_booking",
    "log_booking_action": "audit",
    "confirm_flight_booking": "amadeus_booking",
}


async def _execute_booking_tool(tool_name: str, tool_input: dict, db, user_id: int) -> dict:
    from app.agent.mcp import amadeus_booking, reservation_booking, audit

    module_name = _TOOL_DISPATCH_BOOKING.get(tool_name)
    if module_name == "amadeus_booking":
        return await amadeus_booking.execute_tool(tool_name, tool_input, db, user_id)
    elif module_name == "reservation_booking":
        return await reservation_booking.execute_tool(tool_name, tool_input, db, user_id)
    elif module_name == "audit":
        return await audit.execute_tool(tool_name, tool_input, db, user_id)
    return {"error": f"Tool '{tool_name}' not available in booking sub-agent"}


async def run_booking(context: dict, db) -> dict:
    """Execute a booking using an ephemeral Claude conversation.

    Args:
        context: {
            trip_id, item_id, user_id,
            booking_type: "hotel"|"restaurant",
            offer_id, offer_snapshot,
            payment_method_id,
            booking_token,
            travelers: [...]
        }
        db: AsyncSession from the calling agent (shared session)

    Returns:
        {"status": "confirmed"|"failed"|"requires_user_action", "booking_ref": "...", "details": {}, "error": "..."}
    """
    if not settings.anthropic_api_key:
        return {"status": "failed", "error": "ANTHROPIC_API_KEY not configured"}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_id = context.get("user_id", 0)

    initial_message = (
        f"Execute this booking transaction:\n\n"
        f"```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        f"Steps:\n"
        f"1. Call log_booking_action with action_type='booking_started' and the context details\n"
        f"2. Check the offer_snapshot for existing booking_ref (idempotency)\n"
        f"3. Call book_hotel (or confirm_restaurant_booking) with the offer data\n"
        f"4. Call log_booking_action with the result (success or failure)\n"
        f"5. Return your final JSON response\n"
    )

    messages = [{"role": "user", "content": initial_message}]
    tools = _get_booking_tools()

    iteration = 0
    final_text = ""

    while iteration < _MAX_ITERATIONS:
        iteration += 1
        t0 = time.monotonic()

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=BOOKING_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("Booking agent iteration %d, elapsed=%dms", iteration, elapsed_ms)

        # Collect response content
        response_blocks = []
        tool_use_blocks = []
        text_blocks = []

        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
                response_blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_use_blocks.append(block)
                response_blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        if text_blocks:
            final_text = text_blocks[-1]

        messages.append({"role": "assistant", "content": response_blocks})

        if response.stop_reason == "end_turn" or not tool_use_blocks:
            break

        # Execute tools
        tool_results = []
        for tool_block in tool_use_blocks:
            tool_name = tool_block.name
            tool_input = tool_block.input

            try:
                result_data = await _execute_booking_tool(tool_name, tool_input, db, user_id)
            except Exception as e:
                logger.exception("Booking tool %s failed", tool_name)
                result_data = {"error": str(e)}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": json.dumps(result_data),
            })

        messages.append({"role": "user", "content": tool_results})

    # Parse final text response as JSON
    if final_text:
        # Try to extract JSON from the final response
        import re
        json_match = re.search(r"\{.*\}", final_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

    logger.warning("Booking sub-agent did not return valid JSON after %d iterations", iteration)
    return {
        "status": "failed",
        "error": "Booking sub-agent did not complete successfully",
        "raw_response": final_text[:500] if final_text else "",
    }
