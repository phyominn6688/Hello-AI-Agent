"""Stripe webhook handler.

POST /webhooks/stripe — no auth header required; Stripe-Signature verification is in-app.
This endpoint is mounted outside the /api/v1 prefix in main.py.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.itinerary import ItineraryItem
from app.workers.utils import inject_system_message

logger = logging.getLogger(__name__)
router = APIRouter()


def _stripe():
    try:
        import stripe as _stripe_lib
        from app.config import settings
        _stripe_lib.api_key = settings.stripe_secret_key
        return _stripe_lib
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events.

    Verified via Stripe-Signature header using the webhook secret.
    Falls back to unsigned processing in dev when stripe_webhook_secret is empty.
    """
    from app.config import settings

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    stripe = _stripe()

    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except stripe.error.SignatureVerificationError:
            logger.warning("Invalid Stripe webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # Dev mode — no signature verification
        import json
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    async with AsyncSessionLocal() as db:
        try:
            if event_type == "payment_intent.succeeded":
                await _handle_payment_intent_succeeded(db, stripe, data_object)
            elif event_type == "payment_intent.payment_failed":
                await _handle_payment_intent_failed(db, data_object)
            elif event_type == "charge.refunded":
                await _handle_charge_refunded(db, data_object)
            else:
                logger.debug("Unhandled Stripe event type: %s", event_type)

            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Error processing Stripe webhook event %s", event_type)
            raise HTTPException(status_code=500, detail="Webhook processing error")

    return {"received": True}


async def _handle_payment_intent_succeeded(db: AsyncSession, stripe, intent: dict) -> None:
    """Capture the payment and mark booking as complete."""
    intent_id = intent.get("id")
    if not intent_id:
        return

    result = await db.execute(
        select(Booking).where(Booking.stripe_payment_intent_id == intent_id)
    )
    booking = result.scalar_one_or_none()

    # Capture the hold (manual capture)
    try:
        captured = stripe.PaymentIntent.capture(intent_id)
        charge_id = None
        charges = captured.get("charges", {}).get("data", [])
        if charges:
            charge_id = charges[0].get("id")
    except Exception as e:
        logger.warning("Failed to capture PaymentIntent %s: %s", intent_id, e)
        charge_id = intent.get("latest_charge")

    if booking:
        booking.stripe_charge_id = charge_id
        # Update associated ItineraryItem booking status
        if booking.item_id:
            item_result = await db.execute(
                select(ItineraryItem).where(ItineraryItem.id == booking.item_id)
            )
            item = item_result.scalar_one_or_none()
            if item:
                item.booking_status = "booked"

        logger.info("Payment captured for booking %d (intent %s)", booking.id, intent_id)
    else:
        logger.warning("No booking found for payment_intent %s", intent_id)


async def _handle_payment_intent_failed(db: AsyncSession, intent: dict) -> None:
    """Record payment failure and notify the agent."""
    intent_id = intent.get("id")
    if not intent_id:
        return

    result = await db.execute(
        select(Booking).where(Booking.stripe_payment_intent_id == intent_id)
    )
    booking = result.scalar_one_or_none()

    if booking:
        # Inject system message so agent informs user
        error_msg = intent.get("last_payment_error", {}).get("message", "Payment failed")
        await inject_system_message(
            booking.trip_id,
            f"[PAYMENT FAILED] The payment for booking (item_id={booking.item_id}) failed: "
            f"{error_msg}. Please inform the user and offer to retry with a different payment method.",
        )
        logger.warning("Payment failed for booking %d (intent %s)", booking.id, intent_id)
    else:
        logger.warning("No booking found for failed payment_intent %s", intent_id)


async def _handle_charge_refunded(db: AsyncSession, charge: dict) -> None:
    """Mark booking as refunded."""
    charge_id = charge.get("id")
    if not charge_id:
        return

    result = await db.execute(
        select(Booking).where(Booking.stripe_charge_id == charge_id)
    )
    booking = result.scalar_one_or_none()

    if booking:
        booking.refunded_at = datetime.now(timezone.utc)
        logger.info("Booking %d marked as refunded (charge %s)", booking.id, charge_id)
    else:
        logger.warning("No booking found for refunded charge %s", charge_id)
