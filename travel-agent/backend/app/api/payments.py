"""Payment endpoints — Stripe SetupIntent, booking confirmation, saved methods.

Requires the `stripe` Python SDK (stripe>=7.0.0).
All calls check settings.stripe_secret_key and fall back to mock responses when empty.
"""
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.deps import booking_limiter, read_limiter, write_limiter
from app.models.booking import Booking
from app.models.itinerary import ItineraryItem, Itinerary
from app.models.trip import Trip
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Stripe client helper ───────────────────────────────────────────────────────


def _stripe():
    """Return configured stripe module or raise if not installed."""
    try:
        import stripe as _stripe_lib
        from app.config import settings
        _stripe_lib.api_key = settings.stripe_secret_key
        return _stripe_lib
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Stripe SDK not installed. Add stripe>=7.0.0 to requirements.txt.",
        )


def _stripe_enabled() -> bool:
    from app.config import settings
    return bool(settings.stripe_secret_key)


# ── User helpers ───────────────────────────────────────────────────────────────


async def _get_user(current: CurrentUser, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.cognito_sub == current.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_or_create_stripe_customer(user: User, db: AsyncSession) -> str:
    """Return Stripe customer ID for user, creating one if needed."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    if not _stripe_enabled():
        mock_id = f"cus_mock_{user.id}"
        user.stripe_customer_id = mock_id
        await db.flush()
        return mock_id

    stripe = _stripe()
    customer = stripe.Customer.create(
        email=user.email,
        name=user.name or "",
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer["id"]
    await db.flush()
    return customer["id"]


# ── Redis booking token helpers ────────────────────────────────────────────────


def _redis_client():
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        return aioredis.from_url(settings.redis_url, decode_responses=True)
    except ImportError:
        return None


async def _store_booking_token(token_hash: str, item_id: int, ttl_seconds: int = 30) -> None:
    r = _redis_client()
    if r is None:
        logger.warning("redis not available — booking token not stored (dev mode)")
        return
    async with r:
        await r.setex(f"booking_token:{token_hash}", ttl_seconds, json.dumps({"item_id": item_id, "used": False}))


# ── Schemas ────────────────────────────────────────────────────────────────────


class SetupIntentOut(BaseModel):
    client_secret: str
    customer_id: str


class ConfirmBookingIn(BaseModel):
    item_id: int
    payment_method_id: str
    booking_type: str  # hotel | flight | restaurant
    booking_payload: Dict[str, Any] = {}


class ConfirmBookingOut(BaseModel):
    booking_token: str
    payment_intent_id: str
    client_secret: str


class PaymentMethodOut(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/payments/setup-intent",
    response_model=SetupIntentOut,
    dependencies=[Depends(write_limiter)],
)
async def create_setup_intent(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe SetupIntent so the frontend can securely save a card."""
    user = await _get_user(current, db)
    customer_id = await _get_or_create_stripe_customer(user, db)
    await db.commit()

    if not _stripe_enabled():
        return SetupIntentOut(
            client_secret="seti_mock_secret_dev",
            customer_id=customer_id,
        )

    stripe = _stripe()
    intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"],
        usage="off_session",
    )
    return SetupIntentOut(
        client_secret=intent["client_secret"],
        customer_id=customer_id,
    )


@router.post(
    "/payments/confirm-booking",
    response_model=ConfirmBookingOut,
    dependencies=[Depends(booking_limiter)],
)
async def confirm_booking(
    body: ConfirmBookingIn,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pre-authorise a payment for a booking.

    1. Validates trip ownership.
    2. Checks BOOKING_ALLOWED flag.
    3. Creates a short-lived booking token (30s TTL, single-use via Redis).
    4. Creates a Stripe PaymentIntent (hold — captured after provider confirms).
    5. Returns booking_token + client_secret for frontend confirmation.
    """
    from app.config import settings

    if not settings.booking_allowed:
        raise HTTPException(status_code=503, detail="Booking is not enabled in this environment")

    user = await _get_user(current, db)

    # Verify item ownership: item → itinerary → trip → user
    result = await db.execute(
        select(ItineraryItem)
        .join(Itinerary, ItineraryItem.itinerary_id == Itinerary.id)
        .join(Trip, Itinerary.trip_id == Trip.id)
        .where(ItineraryItem.id == body.item_id, Trip.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Itinerary item not found")

    # Create booking token (short-lived, single-use)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    await _store_booking_token(token_hash, body.item_id, ttl_seconds=30)

    # Determine amount from item_data (placeholder: 0 if not set)
    amount_cents = int(item.item_data.get("price_cents", 0)) if item.item_data else 0

    if not _stripe_enabled():
        return ConfirmBookingOut(
            booking_token=raw_token,
            payment_intent_id="pi_mock_dev",
            client_secret="pi_mock_dev_secret",
        )

    stripe = _stripe()
    customer_id = await _get_or_create_stripe_customer(user, db)
    await db.commit()

    intent = stripe.PaymentIntent.create(
        amount=max(amount_cents, 100),  # Stripe minimum is 100 cents
        currency=item.item_data.get("currency", "usd").lower() if item.item_data else "usd",
        customer=customer_id,
        payment_method=body.payment_method_id,
        capture_method="manual",  # Hold, capture after provider confirms
        confirm=False,
        metadata={
            "item_id": str(body.item_id),
            "user_id": str(user.id),
            "booking_type": body.booking_type,
            "booking_token_hash": token_hash,
        },
    )

    return ConfirmBookingOut(
        booking_token=raw_token,
        payment_intent_id=intent["id"],
        client_secret=intent["client_secret"],
    )


@router.get(
    "/payments/methods",
    response_model=list[PaymentMethodOut],
    dependencies=[Depends(read_limiter)],
)
async def list_payment_methods(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List saved payment methods for the current user's Stripe customer."""
    user = await _get_user(current, db)

    if not user.stripe_customer_id:
        return []

    if not _stripe_enabled():
        return []

    stripe = _stripe()
    methods = stripe.PaymentMethod.list(
        customer=user.stripe_customer_id,
        type="card",
    )
    return [
        PaymentMethodOut(
            id=pm["id"],
            brand=pm["card"]["brand"],
            last4=pm["card"]["last4"],
            exp_month=pm["card"]["exp_month"],
            exp_year=pm["card"]["exp_year"],
        )
        for pm in methods.get("data", [])
    ]
