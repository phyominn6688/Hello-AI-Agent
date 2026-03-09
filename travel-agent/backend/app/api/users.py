"""User profile and GDPR endpoints."""
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.deps import read_limiter, write_limiter
from app.models.conversation import Conversation
from app.models.itinerary import AgentAction, Alert, Itinerary, ItineraryItem
from app.models.trip import Destination, Trip
from app.models.user import User

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────


class UserProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=256)
    passport_country: Optional[str] = Field(default=None, max_length=3)
    date_of_birth: Optional[date] = None
    preferences: Optional[dict[str, Any]] = None
    travelers: Optional[list[dict[str, Any]]] = None


class UserProfileOut(BaseModel):
    id: int
    email: str
    name: Optional[str]
    passport_country: Optional[str]
    date_of_birth: Optional[date]
    age_declaration_method: Optional[str]
    preferences: dict[str, Any]
    travelers: list[dict[str, Any]]

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _require_user(db: AsyncSession, current: CurrentUser) -> User:
    result = await db.execute(select(User).where(User.cognito_sub == current.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/users/me", response_model=UserProfileOut, dependencies=[Depends(read_limiter)])
async def get_my_profile(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _require_user(db, current)


@router.patch(
    "/users/me", response_model=UserProfileOut, dependencies=[Depends(write_limiter)]
)
async def update_my_profile(
    body: UserProfileUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update profile fields. Setting date_of_birth records a self-declaration."""
    user = await _require_user(db, current)
    updates = body.model_dump(exclude_none=True)

    if "date_of_birth" in updates:
        updates["age_declaration_method"] = "self_declared"

    for field, value in updates.items():
        setattr(user, field, value)

    await db.flush()
    return user


@router.get("/users/me/export", dependencies=[Depends(read_limiter)])
async def export_my_data(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR data portability — returns all data held for the authenticated user."""
    user = await _require_user(db, current)

    trips_result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.destinations))
        .where(Trip.user_id == user.id)
    )
    trips = trips_result.scalars().all()

    trip_ids = [t.id for t in trips]

    conversations = []
    itineraries = []
    agent_actions = []
    alerts = []

    if trip_ids:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.trip_id.in_(trip_ids))
        )
        conversations = conv_result.scalars().all()

        itin_result = await db.execute(
            select(Itinerary)
            .options(selectinload(Itinerary.items))
            .where(Itinerary.trip_id.in_(trip_ids))
        )
        itineraries = itin_result.scalars().all()

        actions_result = await db.execute(
            select(AgentAction).where(AgentAction.trip_id.in_(trip_ids))
        )
        agent_actions = actions_result.scalars().all()

        alerts_result = await db.execute(
            select(Alert).where(Alert.user_id == user.id)
        )
        alerts = alerts_result.scalars().all()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "passport_country": user.passport_country,
            "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "preferences": user.preferences,
            "travelers": user.travelers,
            "created_at": user.created_at.isoformat(),
        },
        "trips": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "start_date": t.start_date.isoformat() if t.start_date else None,
                "end_date": t.end_date.isoformat() if t.end_date else None,
                "destinations": [
                    {"city": d.city, "country": d.country, "arrival_date": d.arrival_date.isoformat() if d.arrival_date else None}
                    for d in t.destinations
                ],
            }
            for t in trips
        ],
        "conversations": [
            {"trip_id": c.trip_id, "messages": c.messages}
            for c in conversations
        ],
        "itineraries": [
            {
                "trip_id": i.trip_id,
                "date": i.date.isoformat(),
                "items": [
                    {"name": item.name, "type": item.type, "start_time": str(item.start_time) if item.start_time else None}
                    for item in i.items
                ],
            }
            for i in itineraries
        ],
        "agent_actions": [
            {"trip_id": a.trip_id, "action_type": a.action_type, "reason": a.reason, "created_at": a.created_at.isoformat()}
            for a in agent_actions
        ],
        "alerts": [
            {"type": a.type, "message": a.message, "created_at": a.created_at.isoformat()}
            for a in alerts
        ],
    }


@router.delete(
    "/users/me",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_limiter)],
)
async def delete_my_account(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR right to erasure — permanently deletes all data for the authenticated user.

    Cascade order:
        AgentActions → Alerts → ItineraryItems → Itineraries
        → Conversations → Destinations → Trips → User
    """
    user = await _require_user(db, current)

    trips_result = await db.execute(select(Trip).where(Trip.user_id == user.id))
    trips = trips_result.scalars().all()
    trip_ids = [t.id for t in trips]

    if trip_ids:
        # Agent action audit logs
        actions_result = await db.execute(
            select(AgentAction).where(AgentAction.trip_id.in_(trip_ids))
        )
        for action in actions_result.scalars().all():
            await db.delete(action)

        # Alerts
        alerts_result = await db.execute(
            select(Alert).where(Alert.user_id == user.id)
        )
        for alert in alerts_result.scalars().all():
            await db.delete(alert)

        # Itinerary items + itineraries
        itin_result = await db.execute(
            select(Itinerary)
            .options(selectinload(Itinerary.items))
            .where(Itinerary.trip_id.in_(trip_ids))
        )
        for itin in itin_result.scalars().all():
            for item in itin.items:
                await db.delete(item)
            await db.delete(itin)

        # Conversations
        conv_result = await db.execute(
            select(Conversation).where(Conversation.trip_id.in_(trip_ids))
        )
        for conv in conv_result.scalars().all():
            await db.delete(conv)

        # Destinations + trips (destinations cascade from trip relationship)
        for trip in trips:
            await db.delete(trip)

    await db.delete(user)
    await db.flush()
