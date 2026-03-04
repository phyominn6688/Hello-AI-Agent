from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class TripStatus(str, Enum):
    planning = "planning"
    active = "active"
    completed = "completed"


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[TripStatus] = mapped_column(
        String(32), default=TripStatus.planning, index=True
    )
    budget_per_person: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    destinations: Mapped[list["Destination"]] = relationship(
        "Destination", back_populates="trip", cascade="all, delete-orphan"
    )


class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    city: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(128))
    country_code: Mapped[str | None] = mapped_column(String(3))  # ISO-3166 alpha-3
    order: Mapped[int] = mapped_column(Integer, default=0)
    arrival_date: Mapped[date | None] = mapped_column(Date)
    departure_date: Mapped[date | None] = mapped_column(Date)

    trip: Mapped["Trip"] = relationship("Trip", back_populates="destinations")
