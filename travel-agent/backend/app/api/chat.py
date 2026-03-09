"""Chat endpoint — SSE streaming for agent responses."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.travel_agent import chat_stream
from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.db.database import get_db
from app.deps import chat_limiter, read_limiter
from app.models.trip import Trip
from app.models.user import User

router = APIRouter()


class ChatRequest(BaseModel):
    message: Annotated[str, Field(min_length=1, max_length=settings.chat_message_max_length)]


async def _get_user_id(current: CurrentUser, db: AsyncSession) -> int:
    result = await db.execute(select(User).where(User.cognito_sub == current.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found — start a trip first")
    return user.id


@router.post("/trips/{trip_id}/chat", dependencies=[Depends(chat_limiter)])
async def chat(
    trip_id: int,
    body: ChatRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming chat endpoint.

    Returns Server-Sent Events with the agent's streamed response.
    Event format:
        data: {"type": "text", "content": "..."}
        data: {"type": "tool_use", "tool": "search_flights", "id": "..."}
        data: {"type": "tool_result", "tool": "search_flights", "result": {...}}
        data: {"type": "done"}
    """
    user_id = await _get_user_id(current, db)

    # Verify trip ownership
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Trip not found")

    async def event_stream():
        async for chunk in chat_stream(trip_id, body.message, db):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/trips/{trip_id}/conversation", dependencies=[Depends(read_limiter)])
async def get_conversation(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return conversation history for a trip (display messages only)."""
    from app.models.conversation import Conversation

    user_id = await _get_user_id(current, db)
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Trip not found")

    result = await db.execute(
        select(Conversation).where(Conversation.trip_id == trip_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        return {"messages": []}

    return {"messages": _display_messages(conv.messages)}


def _display_messages(messages: list) -> list:
    """Filter and flatten stored messages for UI display.

    Stored messages may include tool-call and tool-result turns (role=user with
    list content). These are internal agent mechanics — strip them and only return
    human/assistant text turns.
    """
    out = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        # Skip tool-result turns (role=user, content is a list of tool_result blocks)
        if isinstance(content, list):
            if all(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            ):
                continue
            # Extract text from assistant content blocks
            text = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        else:
            text = content or ""

        if text:
            out.append({"role": role, "content": text, "timestamp": m.get("timestamp")})
    return out
