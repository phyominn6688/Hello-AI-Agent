"""Background worker — sends push notifications via SNS."""
import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
QUEUE_URL = os.environ.get("QUEUE_URL", "http://localhost:4566/000000000000/travel-agent-notifications")


async def send_push_notification(user_id: int, trip_id: int, message: str, alert_type: str) -> None:
    """Publish push notification to SNS topic."""
    if not SNS_TOPIC_ARN:
        logger.info(f"[MOCK PUSH] user={user_id} trip={trip_id}: {message}")
        return

    try:
        import boto3

        sns = boto3.client("sns", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps({
                "user_id": user_id,
                "trip_id": trip_id,
                "message": message,
                "type": alert_type,
            }),
            MessageAttributes={
                "type": {"DataType": "String", "StringValue": alert_type},
            },
        )
    except Exception as e:
        logger.error(f"SNS publish failed: {e}")


async def run() -> None:
    logger.info("Notifier worker started")
    try:
        import boto3

        sqs = boto3.client("sqs", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
    except ImportError:
        logger.warning("boto3 not available — notifier worker in mock mode")
        while True:
            await asyncio.sleep(60)

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )
            for msg in response.get("Messages", []):
                body = json.loads(msg.get("Body", "{}"))
                await send_push_notification(
                    user_id=body.get("user_id"),
                    trip_id=body.get("trip_id"),
                    message=body.get("message", ""),
                    alert_type=body.get("type", "info"),
                )
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
        except Exception:
            logger.exception("Notifier loop error")
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
