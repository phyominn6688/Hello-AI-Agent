"""Trip and Destination CRUD endpoints."""
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.models.trip import Destination, Trip, TripStatus
from app.models.user import User

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────


class DestinationCreate(BaseModel):
    city: str
    country: str
    country_code: Optional[str] = None
    order: int = 0
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None


class DestinationOut(DestinationCreate):
    id: int
    trip_id: int

    class Config:
        from_attributes = True


class TripCreate(BaseModel):
    title: str
    budget_per_person: Optional[float] = None
    currency: str = "USD"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    destinations: List[DestinationCreate] = []


class TripUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[TripStatus] = None
    budget_per_person: Optional[float] = None
    currency: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class TripOut(BaseModel):
    id: int
    user_id: int
    title: str
    status: TripStatus
    budget_per_person: Optional[float]
    currency: str
    start_date: Optional[date]
    end_date: Optional[date]
    destinations: List[DestinationOut] = []

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_or_create_user(db: AsyncSession, current: CurrentUser) -> User:
    result = await db.execute(
        select(User).where(User.cognito_sub == current.sub)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            cognito_sub=current.sub,
            email=current.email,
            name=current.name,
        )
        db.add(user)
        await db.flush()
    return user


async def _get_trip_for_user(
    trip_id: int, user_id: int, db: AsyncSession
) -> Trip:
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.destinations))
        .where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/trips", response_model=List[TripOut])
async def list_trips(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.destinations))
        .where(Trip.user_id == user.id)
        .order_by(Trip.created_at.desc())
    )
    return result.scalars().all()


@router.post("/trips", response_model=TripOut, status_code=status.HTTP_201_CREATED)
async def create_trip(
    body: TripCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    trip = Trip(
        user_id=user.id,
        title=body.title,
        budget_per_person=body.budget_per_person,
        currency=body.currency,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(trip)
    await db.flush()

    for d in body.destinations:
        db.add(Destination(trip_id=trip.id, **d.model_dump()))

    await db.flush()
    await db.refresh(trip, ["destinations"])
    return trip


@router.get("/trips/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    return await _get_trip_for_user(trip_id, user.id, db)


@router.patch("/trips/{trip_id}", response_model=TripOut)
async def update_trip(
    trip_id: int,
    body: TripUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    trip = await _get_trip_for_user(trip_id, user.id, db)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(trip, field, value)

    await db.flush()
    return trip


@router.delete("/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    trip = await _get_trip_for_user(trip_id, user.id, db)
    await db.delete(trip)


@router.post("/trips/{trip_id}/destinations", response_model=DestinationOut)
async def add_destination(
    trip_id: int,
    body: DestinationCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    await _get_trip_for_user(trip_id, user.id, db)
    dest = Destination(trip_id=trip_id, **body.model_dump())
    db.add(dest)
    await db.flush()
    return dest
