"""SQS batch consumer entry point for processing orders."""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response,
)
from aws_lambda_powertools.utilities.batch.types import PartialItemFailureResponse
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from shared.envelope import EventEnvelope

from process_order.factory import OrderHandlerFactory, UnsupportedSourceError

logger = Logger(service="process_order")
metrics = Metrics(namespace="ProcessOrder", service="process_order")

processor = BatchProcessor(EventType.SQS)


def record_handler(record: SQSRecord) -> Any:
    """Process a single SQS record containing an EventEnvelope.

    Uses OrderHandlerFactory to resolve the provider handler dynamically
    from envelope.source without coupling process_order to any specific provider.
    """
    body = record.body
    envelope = EventEnvelope.from_json(body)

    try:
        handler = OrderHandlerFactory.get_handler(envelope.source)
    except UnsupportedSourceError:
        logger.error(
            "Unsupported order event source '%s'. RequestId: %s",
            envelope.source,
            envelope.request_id,
            extra={"source": envelope.source, "request_id": envelope.request_id},
        )
        # Poison pill mitigation: Acknowledge and drop unrecognized sources
        # so they do not exhaust 5 retries and block SQS FIFO message groups.
        return None

    return handler.handle(envelope)


@logger.inject_lambda_context
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict[str, Any], context: Any) -> PartialItemFailureResponse:
    """Process incoming SQS messages containing order events."""
    return process_partial_response(
        event=event, context=context, processor=processor, record_handler=record_handler
    )
