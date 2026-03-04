from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ItemType(str, Enum):
    flight = "flight"
    hotel = "hotel"
    restaurant = "restaurant"
    event = "event"
    activity = "activity"
    train = "train"
    transfer = "transfer"


class Flexibility(str, Enum):
    fixed = "fixed"       # Hard constraint — cannot move
    flexible = "flexible" # Can reorder within day
    droppable = "droppable"  # Can be skipped if needed


class WishlistStatus(str, Enum):
    wishlist = "wishlist"
    available = "available"
    booked = "booked"
    unavailable = "unavailable"
    replaced = "replaced"


class Itinerary(Base):
    __tablename__ = "itineraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    destination_id: Mapped[int | None] = mapped_column(ForeignKey("destinations.id"))
    date: Mapped[date] = mapped_column(Date, index=True)

    items: Mapped[list["ItineraryItem"]] = relationship(
        "ItineraryItem", back_populates="itinerary", cascade="all, delete-orphan"
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id"), index=True)

    type: Mapped[ItemType] = mapped_column(String(32))
    flexibility: Mapped[Flexibility] = mapped_column(
        String(32), default=Flexibility.flexible
    )
    name: Mapped[str] = mapped_column(String(256))
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    duration_mins: Mapped[int | None] = mapped_column(Integer)

    # {"lat": 40.7128, "lng": -74.0060, "address": "...", "place_id": "..."}
    location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    booking_ref: Mapped[str | None] = mapped_column(String(128))
    booking_status: Mapped[str | None] = mapped_column(String(64))
    confirmation_doc_url: Mapped[str | None] = mapped_column(Text)  # S3 URL
    wallet_pass_url: Mapped[str | None] = mapped_column(Text)       # Apple/Google pass

    wishlist_status: Mapped[WishlistStatus] = mapped_column(
        String(32), default=WishlistStatus.wishlist
    )

    # API-specific data: price, seats, amenities, deep-link, etc.
    # Note: "metadata" is reserved by SQLAlchemy DeclarativeBase — using item_data
    item_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    itinerary: Mapped["Itinerary"] = relationship(
        "Itinerary", back_populates="items"
    )


class AgentAction(Base):
    """Audit log of autonomous agent actions."""
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("itinerary_items.id"))
    action_type: Mapped[str] = mapped_column(
        String(32)
    )  # cancel | rebook | modify | notify
    reason: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(
        String(64)
    )  # flight_change | cancellation | weather | reminder | leave_now
    message: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
