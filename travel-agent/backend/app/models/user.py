from datetime import date, datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    cognito_sub: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(256))
    avatar: Mapped[str | None] = mapped_column(Text)
    passport_country: Mapped[str | None] = mapped_column(String(3))  # ISO-3166 alpha-3

    # GPS location — updated by the frontend during active trips
    current_lat: Mapped[float | None] = mapped_column(Float)
    current_lng: Mapped[float | None] = mapped_column(Float)
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Age verification — self-declared; declaration_method tracks assurance level
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    age_declaration_method: Mapped[str | None] = mapped_column(
        String(32)
    )  # "self_declared" — expand in future iterations

    # {"dietary": ["vegetarian"], "mobility": "wheelchair", "interests": ["hiking"]}
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # [{"type": "adult"}, {"type": "child", "age": 8}]
    travelers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
