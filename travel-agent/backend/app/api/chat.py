"""Chat endpoint — SSE streaming for agent responses."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.travel_agent import chat_stream
from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.models.trip import Trip
from app.models.user import User

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


async def _get_user_id(current: CurrentUser, db: AsyncSession) -> int:
    result = await db.execute(select(User).where(User.cognito_sub == current.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found — start a trip first")
    return user.id


@router.post("/trips/{trip_id}/chat")
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


@router.get("/trips/{trip_id}/conversation")
async def get_conversation(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return full conversation history for a trip."""
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

    # Return messages without internal timestamps stripped for the UI
    return {
        "messages": [
            {"role": m["role"], "content": m["content"], "timestamp": m.get("timestamp")}
            for m in conv.messages
        ]
    }
