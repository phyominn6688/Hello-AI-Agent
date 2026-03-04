"""Background worker — polls flight status and triggers cascade replanning.

Runs as a separate ECS task (or Lambda) consuming from the SQS queue.
Zero FastAPI dependency — runs standalone.
"""
import asyncio
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)
QUEUE_URL = os.environ.get("QUEUE_URL", "http://localhost:4566/000000000000/travel-agent")


async def _receive_messages() -> list[dict]:
    """Receive messages from SQS (via LocalStack in dev, real SQS in prod)."""
    try:
        import boto3

        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            MessageAttributeNames=["All"],
        )
        return response.get("Messages", [])
    except Exception as e:
        logger.warning(f"SQS receive failed: {e}")
        return []


async def _delete_message(receipt_handle: str) -> None:
    try:
        import boto3

        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
    except Exception as e:
        logger.warning(f"SQS delete failed: {e}")


async def process_flight_status_check(message: dict) -> None:
    """Check flight status and update itinerary item if changed."""
    body = json.loads(message.get("Body", "{}"))
    item_id = body.get("item_id")
    booking_ref = body.get("booking_ref")
    flight_number = body.get("flight_number")
    trip_id = body.get("trip_id")

    logger.info(f"Checking flight status: {flight_number} (item {item_id})")

    # In prod: call Amadeus Flight Status API
    # For now: log and acknowledge
    # On status change: publish alert to SNS, update DB, trigger agent replanning


async def run() -> None:
    """Main worker loop — long-poll SQS, process messages."""
    logger.info("Flight monitor worker started")
    while True:
        messages = await _receive_messages()
        for msg in messages:
            try:
                attrs = msg.get("MessageAttributes", {})
                msg_type = attrs.get("type", {}).get("StringValue", "")
                if msg_type == "flight_status_check":
                    await process_flight_status_check(msg)
                await _delete_message(msg["ReceiptHandle"])
            except Exception:
                logger.exception(f"Failed to process message {msg.get('MessageId')}")
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
