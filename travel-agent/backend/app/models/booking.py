"""Booking ORM model — tracks payment and provider booking records."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Optional link to itinerary item (may be null for standalone bookings)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("itinerary_items.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), nullable=False, index=True)

    # Stripe identifiers
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(128))
    stripe_charge_id: Mapped[str | None] = mapped_column(String(128))

    # Amount in smallest currency unit (e.g. cents for USD)
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))

    # Provider booking reference (e.g. Amadeus PNR, OpenTable confirmation number)
    booking_ref: Mapped[str | None] = mapped_column(String(256))
    provider: Mapped[str | None] = mapped_column(
        String(64)
    )  # amadeus | opentable | manual | etc.

    # Full provider API response for debugging and record-keeping
    raw_provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
