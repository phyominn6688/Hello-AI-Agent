"""Trip and Destination CRUD endpoints."""
from datetime import date
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.deps import read_limiter, write_limiter
from app.models.trip import Destination, Trip, TripStatus
from app.models.user import User

router = APIRouter()

# ISO 4217 currency codes (common subset — extend as needed)
_VALID_CURRENCIES = frozenset({
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
    "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
    "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
    "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR", "ILS",
    "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR",
    "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD",
    "LSL", "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU",
    "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK",
    "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
    "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK",
    "SGD", "SHP", "SLL", "SOS", "SRD", "STN", "SVC", "SYP", "SZL", "THB",
    "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX",
    "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST", "XAF", "XCD", "XOF",
    "XPF", "YER", "ZAR", "ZMW", "ZWL",
})


# ── Schemas ────────────────────────────────────────────────────────────────────


class DestinationCreate(BaseModel):
    city: Annotated[str, Field(max_length=128)]
    country: Annotated[str, Field(max_length=128)]
    country_code: Optional[Annotated[str, Field(max_length=3)]] = None
    order: int = 0
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None


class DestinationOut(DestinationCreate):
    id: int
    trip_id: int

    class Config:
        from_attributes = True


class TripCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    budget_per_person: Optional[float] = None
    currency: str = "USD"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    destinations: List[DestinationCreate] = []

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        code = v.upper()
        if code not in _VALID_CURRENCIES:
            raise ValueError(f"'{v}' is not a valid ISO 4217 currency code")
        return code


class TripUpdate(BaseModel):
    title: Optional[Annotated[str, Field(min_length=1, max_length=200)]] = None
    status: Optional[TripStatus] = None
    budget_per_person: Optional[float] = None
    currency: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        code = v.upper()
        if code not in _VALID_CURRENCIES:
            raise ValueError(f"'{v}' is not a valid ISO 4217 currency code")
        return code


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
    if user:
        return user

    # Guard against concurrent inserts for the same sub (race condition)
    try:
        user = User(
            cognito_sub=current.sub,
            email=current.email,
            name=current.name,
        )
        db.add(user)
        await db.flush()
        return user
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(User).where(User.cognito_sub == current.sub)
        )
        return result.scalar_one()


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


@router.get("/trips", response_model=List[TripOut], dependencies=[Depends(read_limiter)])
async def list_trips(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.destinations))
        .where(Trip.user_id == user.id)
        .order_by(Trip.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post(
    "/trips",
    response_model=TripOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_limiter)],
)
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


@router.get("/trips/{trip_id}", response_model=TripOut, dependencies=[Depends(read_limiter)])
async def get_trip(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    return await _get_trip_for_user(trip_id, user.id, db)


@router.patch(
    "/trips/{trip_id}", response_model=TripOut, dependencies=[Depends(write_limiter)]
)
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


@router.delete(
    "/trips/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_limiter)],
)
async def delete_trip(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_or_create_user(db, current)
    trip = await _get_trip_for_user(trip_id, user.id, db)
    await db.delete(trip)


@router.post(
    "/trips/{trip_id}/destinations",
    response_model=DestinationOut,
    dependencies=[Depends(write_limiter)],
)
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
