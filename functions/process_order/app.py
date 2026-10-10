"""SQS batch consumer entry point for processing orders."""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from shared.envelope import EventEnvelope

logger = Logger(service="process_order")


@logger.inject_lambda_context
def lambda_handler(
    event: dict[str, Any], context: LambdaContext | object
) -> dict[str, Any]:
    """Process incoming SQS messages containing Zalo order events."""
    batch_item_failures: list[dict[str, str]] = []

    records = event.get("Records", [])
    logger.info("Received batch of %d records", len(records))

    for record in records:
        message_id = record.get("messageId", "")
        try:
            body = record.get("body", "")
            envelope = EventEnvelope.from_json(body)
            logger.info(
                "Processing event from request %s",
                envelope.request_id,
                extra={"request_id": envelope.request_id},
            )
        except Exception:
            logger.exception("Failed to process message %s", message_id)
            if message_id:
                batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
