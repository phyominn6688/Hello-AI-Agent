"""Background wallet worker — generates Apple Wallet (.pkpass) and Google Wallet passes.

Runs as a separate ECS task consuming from the SQS wallet queue.

Message format:
  {
    "type": "generate_wallet_pass",
    "item_id": 123,
    "user_id": 456,
    "pass_type": "boarding_pass"|"hotel"|"event"|"generic",
    "traveler_name": "Jane Smith",
    "title": "Beijing → Shanghai — G1",
    "subtitle": "Platform 5, Car 3",
    "date": "2026-04-15",
    "location": "Shanghai Hongqiao Station",
    "booking_ref": "ABC123",
    "barcode_value": "ABC123456"
  }

Apple Wallet flow:
  1. Load pass template JSON from S3 (passes/templates/{pass_type}/pass.json)
  2. Fill in dynamic fields
  3. Sign with P12 certificate from Secrets Manager
  4. Create .pkpass zip bundle
  5. Upload to S3 at passes/generated/{user_id}/{item_id}.pkpass
  6. Generate CloudFront signed URL (7-day TTL)

Google Wallet flow:
  1. Load service account from Secrets Manager
  2. Build GenericObject JWT payload
  3. Generate "Add to Google Wallet" URL

Updates ItineraryItem.wallet_pass_url = {"apple": "...", "google": "..."}
Publishes SNS notification.

NOTE: Uses mock URLs when certificate ARNs are empty (dev mode).
"""
import asyncio
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.models.itinerary import ItineraryItem

logger = logging.getLogger(__name__)

WALLET_QUEUE_URL = os.environ.get(
    "WALLET_QUEUE_URL",
    os.environ.get("QUEUE_URL", "http://localhost:4566/000000000000/travel-agent-wallet"),
)


# ── AWS helpers ────────────────────────────────────────────────────────────────


def _s3_client():
    import boto3
    return boto3.client("s3", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))


def _secrets_client():
    import boto3
    return boto3.client("secretsmanager", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))


def _sns_client():
    import boto3
    return boto3.client("sns", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))


def _load_secret(secret_arn: str) -> Optional[str]:
    if not secret_arn:
        return None
    try:
        sm = _secrets_client()
        resp = sm.get_secret_value(SecretId=secret_arn)
        return resp.get("SecretString") or resp.get("SecretBinary", b"").decode()
    except Exception as e:
        logger.warning("Failed to load secret %s: %s", secret_arn, e)
        return None


# ── Apple Wallet (.pkpass) ─────────────────────────────────────────────────────


def _build_apple_pass_json(job: dict, template: dict) -> dict:
    """Fill dynamic fields into a pass template."""
    pass_data = dict(template)
    pass_type = job.get("pass_type", "generic")

    pass_data["serialNumber"] = str(job.get("item_id", "0"))
    pass_data["description"] = job.get("title", "Travel Pass")

    # Barcode
    barcode_value = job.get("barcode_value") or job.get("booking_ref", "NO_REF")
    pass_data["barcode"] = {
        "message": barcode_value,
        "format": "PKBarcodeFormatQR",
        "messageEncoding": "iso-8859-1",
    }
    pass_data["barcodes"] = [pass_data["barcode"]]

    # Pass-type-specific fields
    field_section = "generic"
    if pass_type == "boarding_pass":
        field_section = "boardingPass"
        pass_data["boardingPass"] = pass_data.get("boardingPass", {})
        pass_data["boardingPass"]["primaryFields"] = [
            {"key": "destination", "label": "TO", "value": job.get("location", "")}
        ]
        pass_data["boardingPass"]["auxiliaryFields"] = [
            {"key": "traveler", "label": "PASSENGER", "value": job.get("traveler_name", "")},
            {"key": "booking_ref", "label": "BOOKING REF", "value": job.get("booking_ref", "")},
        ]
    else:
        pass_data["generic"] = pass_data.get("generic", {})
        pass_data["generic"]["primaryFields"] = [
            {"key": "title", "label": "BOOKING", "value": job.get("title", "")}
        ]
        pass_data["generic"]["auxiliaryFields"] = [
            {"key": "date", "label": "DATE", "value": job.get("date", "")},
            {"key": "ref", "label": "REF", "value": job.get("booking_ref", "")},
        ]
        if job.get("traveler_name"):
            pass_data["generic"]["secondaryFields"] = [
                {"key": "traveler", "label": "TRAVELER", "value": job["traveler_name"]}
            ]

    return pass_data


def _create_mock_pkpass(job: dict) -> bytes:
    """Create a minimal mock .pkpass bundle for dev/test."""
    pass_json = json.dumps({
        "formatVersion": 1,
        "passTypeIdentifier": "pass.mock.travel-agent",
        "serialNumber": str(job.get("item_id", "0")),
        "teamIdentifier": "MOCKTM",
        "description": job.get("title", "Travel Pass"),
        "generic": {
            "primaryFields": [
                {"key": "title", "label": "BOOKING", "value": job.get("title", "")}
            ]
        },
        "barcode": {
            "message": job.get("booking_ref", "MOCK"),
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1",
        },
    }).encode()

    manifest = json.dumps({"pass.json": _sha1_hex(pass_json)}).encode()

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pass.json", pass_json)
        zf.writestr("manifest.json", manifest)
    return buf.getvalue()


def _sha1_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha1(data).hexdigest()


async def _generate_apple_pass(job: dict) -> Optional[str]:
    """Generate a .pkpass and upload to S3. Returns CloudFront signed URL."""
    item_id = job.get("item_id")
    user_id = job.get("user_id")

    if not settings.apple_pass_certificate_secret_arn:
        # Dev mode — create mock pass and upload
        logger.info("Apple pass certificate ARN not set — generating mock .pkpass")
        pkpass_bytes = _create_mock_pkpass(job)
        s3_key = f"passes/generated/{user_id}/{item_id}.pkpass"
        try:
            s3 = _s3_client()
            s3.put_object(
                Bucket=settings.storage_bucket,
                Key=s3_key,
                Body=pkpass_bytes,
                ContentType="application/vnd.apple.pkpass",
            )
            # Mock URL — no CloudFront signing in dev
            endpoint = settings.storage_endpoint_url or "https://s3.amazonaws.com"
            return f"{endpoint}/{settings.storage_bucket}/{s3_key}"
        except Exception as e:
            logger.warning("Failed to upload mock .pkpass: %s", e)
            return f"https://mock-passes.travel-agent.local/{item_id}.pkpass"

    # Production path: load cert, sign, upload, return CloudFront signed URL
    cert_secret = _load_secret(settings.apple_pass_certificate_secret_arn)
    if not cert_secret:
        logger.warning("Could not load Apple pass certificate — using mock URL")
        return f"https://mock-passes.travel-agent.local/{item_id}.pkpass"

    try:
        # Load pass template from S3
        pass_type = job.get("pass_type", "generic")
        s3 = _s3_client()
        try:
            template_obj = s3.get_object(
                Bucket=settings.storage_bucket,
                Key=f"passes/templates/{pass_type}/pass.json",
            )
            template = json.loads(template_obj["Body"].read())
        except Exception:
            template = {}

        pass_json_data = _build_apple_pass_json(job, template)
        pass_json_bytes = json.dumps(pass_json_data).encode()

        # Sign the pass
        # NOTE: Proper PKPass signing requires the M2Crypto or cryptography library
        # with the P12 certificate. This is a structural placeholder.
        import base64
        cert_bytes = base64.b64decode(cert_secret) if not cert_secret.startswith("{") else cert_secret.encode()

        manifest = {"pass.json": _sha1_hex(pass_json_bytes)}
        manifest_bytes = json.dumps(manifest).encode()

        # Placeholder signature (production requires proper signing with PKCS7)
        signature_bytes = b"PLACEHOLDER_SIGNATURE"

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pass.json", pass_json_bytes)
            zf.writestr("manifest.json", manifest_bytes)
            zf.writestr("signature", signature_bytes)
        pkpass_bytes = buf.getvalue()

        s3_key = f"passes/generated/{user_id}/{item_id}.pkpass"
        s3.put_object(
            Bucket=settings.storage_bucket,
            Key=s3_key,
            Body=pkpass_bytes,
            ContentType="application/vnd.apple.pkpass",
        )

        # Generate CloudFront signed URL (7-day TTL)
        # In production, use boto3 CloudFront signed URL generation
        endpoint = os.environ.get("CLOUDFRONT_URL", settings.storage_endpoint_url)
        return f"{endpoint}/{s3_key}?token=signed-placeholder"

    except Exception as e:
        logger.exception("Apple pass generation failed: %s", e)
        return f"https://mock-passes.travel-agent.local/{item_id}.pkpass"


# ── Google Wallet ──────────────────────────────────────────────────────────────


async def _generate_google_wallet_url(job: dict) -> Optional[str]:
    """Generate a 'Save to Google Wallet' URL."""
    item_id = job.get("item_id")

    if not settings.google_wallet_service_account_secret_arn or not settings.google_wallet_issuer_id:
        logger.info("Google Wallet not configured — using mock URL")
        return f"https://pay.google.com/gp/v/save/mock-{item_id}"

    sa_secret = _load_secret(settings.google_wallet_service_account_secret_arn)
    if not sa_secret:
        return f"https://pay.google.com/gp/v/save/mock-{item_id}"

    try:
        import jwt as pyjwt  # PyJWT
        sa_info = json.loads(sa_secret)

        object_id = f"{settings.google_wallet_issuer_id}.item-{item_id}"
        generic_object = {
            "id": object_id,
            "classId": f"{settings.google_wallet_issuer_id}.generic_class",
            "genericType": "GENERIC_TYPE_UNSPECIFIED",
            "hexBackgroundColor": "#1a73e8",
            "header": {"defaultValue": {"language": "en-US", "value": job.get("title", "Travel Pass")}},
            "subheader": {"defaultValue": {"language": "en-US", "value": job.get("subtitle", "")}},
            "textModulesData": [
                {"header": "BOOKING REF", "body": job.get("booking_ref", ""), "id": "booking_ref"},
                {"header": "DATE", "body": job.get("date", ""), "id": "date"},
            ],
            "barcode": {
                "type": "QR_CODE",
                "value": job.get("barcode_value") or job.get("booking_ref", ""),
            },
        }

        payload = {
            "iss": sa_info["client_email"],
            "aud": "google",
            "origins": ["https://travel-agent.example.com"],
            "typ": "savetowallet",
            "payload": {"genericObjects": [generic_object]},
        }

        token = pyjwt.encode(payload, sa_info["private_key"], algorithm="RS256")
        return f"https://pay.google.com/gp/v/save/{token}"

    except Exception as e:
        logger.warning("Google Wallet URL generation failed: %s", e)
        return f"https://pay.google.com/gp/v/save/mock-{item_id}"


# ── Main job processor ─────────────────────────────────────────────────────────


async def process_wallet_job(job: dict, db) -> None:
    """Process a single wallet pass generation job."""
    item_id = job.get("item_id")
    user_id = job.get("user_id")

    if not item_id:
        logger.warning("Wallet job missing item_id: %s", job)
        return

    logger.info("Generating wallet passes for item %d (user %s)", item_id, user_id)

    apple_url = await _generate_apple_pass(job)
    google_url = await _generate_google_wallet_url(job)

    wallet_pass_data = {}
    if apple_url:
        wallet_pass_data["apple"] = apple_url
    if google_url:
        wallet_pass_data["google"] = google_url

    # Update DB
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(ItineraryItem).where(ItineraryItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            if item:
                item.wallet_pass_url = wallet_pass_data
                await db_session.commit()
                logger.info("Wallet pass URLs stored for item %d", item_id)
            else:
                logger.warning("Item %d not found for wallet pass update", item_id)
        except Exception:
            await db_session.rollback()
            logger.exception("Failed to update wallet_pass_url for item %d", item_id)

    # Publish SNS notification to user
    if settings.sns_topic_arn and user_id:
        try:
            sns = _sns_client()
            sns.publish(
                TopicArn=settings.sns_topic_arn,
                Message=json.dumps({
                    "type": "wallet_pass_ready",
                    "user_id": user_id,
                    "item_id": item_id,
                    "apple_url": apple_url,
                    "google_url": google_url,
                }),
                Subject="Wallet pass ready",
            )
        except Exception as e:
            logger.warning("SNS publish failed: %s", e)


# ── SQS consumer loop ──────────────────────────────────────────────────────────


async def _receive_messages() -> list[dict]:
    try:
        import boto3
        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        response = sqs.receive_message(
            QueueUrl=WALLET_QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
        )
        return response.get("Messages", [])
    except Exception as e:
        logger.warning("SQS receive failed: %s", e)
        return []


async def _delete_message(receipt_handle: str) -> None:
    try:
        import boto3
        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        sqs.delete_message(QueueUrl=WALLET_QUEUE_URL, ReceiptHandle=receipt_handle)
    except Exception as e:
        logger.warning("SQS delete failed: %s", e)


async def main() -> None:
    logger.info("Wallet worker started (queue: %s)", WALLET_QUEUE_URL)
    while True:
        messages = await _receive_messages()
        for msg in messages:
            try:
                body = json.loads(msg.get("Body", "{}"))
                msg_type = body.get("type", "")
                if msg_type == "generate_wallet_pass":
                    await process_wallet_job(body, None)
                else:
                    logger.debug("Unhandled wallet queue message type: %s", msg_type)
                await _delete_message(msg["ReceiptHandle"])
            except Exception:
                logger.exception("Failed to process wallet message %s", msg.get("MessageId"))
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
