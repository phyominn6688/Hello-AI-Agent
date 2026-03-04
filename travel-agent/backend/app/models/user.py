from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text
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
