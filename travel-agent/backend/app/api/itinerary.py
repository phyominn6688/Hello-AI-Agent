"""Itinerary and ItineraryItem CRUD."""
from datetime import date, time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.deps import read_limiter, write_limiter
from app.models.itinerary import (
    AgentAction,
    Alert,
    Flexibility,
    Itinerary,
    ItineraryItem,
    ItemType,
    WishlistStatus,
)
from app.models.trip import Trip
from app.models.user import User

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────


class ItemCreate(BaseModel):
    type: ItemType
    flexibility: Flexibility = Flexibility.flexible
    name: str
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    duration_mins: Optional[int] = None
    location: Optional[Dict[str, Any]] = None
    booking_ref: Optional[str] = None
    booking_status: Optional[str] = None
    wishlist_status: WishlistStatus = WishlistStatus.wishlist
    item_data: Dict[str, Any] = {}


class ItemUpdate(BaseModel):
    flexibility: Optional[Flexibility] = None
    name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    duration_mins: Optional[int] = None
    location: Optional[Dict[str, Any]] = None
    booking_ref: Optional[str] = None
    booking_status: Optional[str] = None
    wishlist_status: Optional[WishlistStatus] = None
    item_data: Optional[Dict[str, Any]] = None


class ItemOut(BaseModel):
    id: int
    itinerary_id: int
    type: ItemType
    flexibility: Flexibility
    name: str
    start_time: Optional[time]
    end_time: Optional[time]
    duration_mins: Optional[int]
    location: Optional[Dict[str, Any]]
    booking_ref: Optional[str]
    booking_status: Optional[str]
    confirmation_doc_url: Optional[str]
    wallet_pass_url: Optional[str]
    wishlist_status: WishlistStatus
    item_data: Dict[str, Any]

    class Config:
        from_attributes = True


class ItineraryOut(BaseModel):
    id: int
    trip_id: int
    destination_id: Optional[int]
    date: date
    items: List[ItemOut] = []

    class Config:
        from_attributes = True


class AlertOut(BaseModel):
    id: int
    trip_id: int
    type: str
    message: str
    read_at: Optional[Any]
    created_at: Any

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _assert_trip_owned(trip_id: int, user_id: int, db: AsyncSession) -> None:
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Trip not found")


async def _get_user_id(current: CurrentUser, db: AsyncSession) -> int:
    from app.models.user import User

    result = await db.execute(select(User).where(User.cognito_sub == current.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.id


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/trips/{trip_id}/itinerary", response_model=List[ItineraryOut])
async def get_itinerary(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    result = await db.execute(
        select(Itinerary)
        .options(selectinload(Itinerary.items))
        .where(Itinerary.trip_id == trip_id)
        .order_by(Itinerary.date)
    )
    return result.scalars().all()


@router.post(
    "/trips/{trip_id}/itinerary/{itinerary_date}/items",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_item(
    trip_id: int,
    itinerary_date: date,
    body: ItemCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    # Get or create the day's itinerary
    result = await db.execute(
        select(Itinerary).where(
            Itinerary.trip_id == trip_id, Itinerary.date == itinerary_date
        )
    )
    itin = result.scalar_one_or_none()
    if not itin:
        itin = Itinerary(trip_id=trip_id, date=itinerary_date)
        db.add(itin)
        await db.flush()

    item = ItineraryItem(itinerary_id=itin.id, **body.model_dump())
    db.add(item)
    await db.flush()
    return item


@router.patch("/trips/{trip_id}/items/{item_id}", response_model=ItemOut)
async def update_item(
    trip_id: int,
    item_id: int,
    body: ItemUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary)
        .where(ItineraryItem.id == item_id, Itinerary.trip_id == trip_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)

    await db.flush()
    return item


@router.get("/trips/{trip_id}/alerts", response_model=List[AlertOut])
async def get_alerts(
    trip_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    result = await db.execute(
        select(Alert)
        .where(Alert.trip_id == trip_id, Alert.user_id == user_id)
        .order_by(Alert.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.post("/trips/{trip_id}/alerts/{alert_id}/read", response_model=AlertOut)
async def mark_alert_read(
    trip_id: int,
    alert_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone

    user_id = await _get_user_id(current, db)
    result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.trip_id == trip_id,
            Alert.user_id == user_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.read_at = datetime.now(timezone.utc)
    await db.flush()
    return alert


# ── Wishlist endpoints ──────────────────────────────────────────────────────────


class WishlistItemOut(BaseModel):
    id: int
    name: str
    type: ItemType
    city: str
    country: str
    notes: str
    estimated_duration_mins: Optional[int]
    wishlist_status: WishlistStatus

    class Config:
        from_attributes = True


class PromoteWishlistIn(BaseModel):
    date: date
    start_time: Optional[time] = None


@router.get(
    "/trips/{trip_id}/wishlist",
    response_model=List[WishlistItemOut],
    dependencies=[Depends(read_limiter)],
)
async def get_wishlist(
    trip_id: int,
    type: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    from datetime import date as date_type
    wishlist_date = date_type(9999, 12, 31)

    result = await db.execute(
        select(Itinerary)
        .options(selectinload(Itinerary.items))
        .where(Itinerary.trip_id == trip_id, Itinerary.date == wishlist_date)
    )
    itin = result.scalar_one_or_none()
    if not itin:
        return []

    items = [i for i in itin.items if i.wishlist_status == WishlistStatus.wishlist]

    if type:
        type_map = {
            "restaurant": ItemType.restaurant,
            "activity": ItemType.activity,
            "event": ItemType.event,
            "hotel": ItemType.hotel,
        }
        mapped = type_map.get(type)
        if mapped:
            items = [i for i in items if i.type == mapped]

    if city:
        items = [
            i for i in items
            if city.lower() in (i.item_data or {}).get("city", "").lower()
        ]

    # Build response manually to include item_data fields
    return [
        WishlistItemOut(
            id=i.id,
            name=i.name,
            type=i.type,
            city=(i.item_data or {}).get("city", ""),
            country=(i.item_data or {}).get("country", ""),
            notes=(i.item_data or {}).get("notes", ""),
            estimated_duration_mins=i.duration_mins,
            wishlist_status=i.wishlist_status,
        )
        for i in items
    ]


@router.post(
    "/trips/{trip_id}/wishlist/{item_id}/promote",
    response_model=ItemOut,
    dependencies=[Depends(write_limiter)],
)
async def promote_wishlist_item(
    trip_id: int,
    item_id: int,
    body: PromoteWishlistIn,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote a wishlist item to scheduled — sets date, time, and wishlist_status='available'."""
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary)
        .where(ItineraryItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")

    # Move item to a date-specific itinerary
    from datetime import date as date_type
    result2 = await db.execute(
        select(Itinerary).where(
            Itinerary.trip_id == trip_id, Itinerary.date == body.date
        )
    )
    target_itin = result2.scalar_one_or_none()
    if not target_itin:
        target_itin = Itinerary(trip_id=trip_id, date=body.date)
        db.add(target_itin)
        await db.flush()

    item.itinerary_id = target_itin.id
    item.wishlist_status = WishlistStatus.available
    if body.start_time:
        item.start_time = body.start_time
    await db.flush()
    return item


@router.delete(
    "/trips/{trip_id}/wishlist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_limiter)],
)
async def remove_wishlist_item(
    trip_id: int,
    item_id: int,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a wishlist item as unavailable (soft delete)."""
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary)
        .where(ItineraryItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")

    item.wishlist_status = WishlistStatus.unavailable
    await db.flush()


# ── Audit log endpoint ──────────────────────────────────────────────────────────


class AgentActionOut(BaseModel):
    id: int
    trip_id: int
    item_id: Optional[int]
    action_type: str
    reason: str
    outcome: Optional[str]
    agent_type: str
    tool_name: Optional[str]
    status: str
    booking_token_hash: Optional[str]
    duration_ms: Optional[int]
    created_at: Any

    class Config:
        from_attributes = True


@router.get(
    "/trips/{trip_id}/audit-log",
    response_model=List[AgentActionOut],
    dependencies=[Depends(read_limiter)],
)
async def get_audit_log(
    trip_id: int,
    status: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated audit log of agent actions for a trip."""
    user_id = await _get_user_id(current, db)
    await _assert_trip_owned(trip_id, user_id, db)

    query = (
        select(AgentAction)
        .where(AgentAction.trip_id == trip_id)
        .order_by(AgentAction.created_at.desc())
    )
    if status:
        query = query.where(AgentAction.status == status)
    if action_type:
        query = query.where(AgentAction.action_type == action_type)

    offset = (page - 1) * page_size
    query = query.limit(page_size).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()
