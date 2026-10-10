"""Zalo Official Account order event handler."""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger
from shared.envelope import EventEnvelope
from shared.zalo.models import UserSendTextEvent
from shared.zalo.parser import InvalidPayloadError, parse_zalo_event

from process_order.registry import register_order_handler

logger = Logger(service="process_order")


@register_order_handler("zalo")
class ZaloOrderHandler:
    """Handles order events originating from Zalo Official Account webhooks.

    Why a dedicated handler?
    Isolates Zalo payload schema parsing, domain event extraction, and error
    classification from generic order routing.
    """

    def handle(self, envelope: EventEnvelope) -> Any:
        """Parse and process a Zalo webhook event from an EventEnvelope."""
        try:
            event = parse_zalo_event(envelope.raw_payload, envelope.occurred_at_utc)
        except InvalidPayloadError:
            # Poison pill: unrecoverable malformed payload.
            # Log and do not fail the record so it doesn't block the SQS FIFO queue.
            logger.error(
                "Discarding malformed Zalo payload. RequestId: %s",
                envelope.request_id,
                extra={"request_id": envelope.request_id},
            )
            return None

        if isinstance(event, UserSendTextEvent):
            logger.info(
                "Received order text from user %s: '%s'",
                event.user_id,
                event.message.text,
                extra={
                    "user_id": event.user_id,
                    "msg_id": event.message.msg_id,
                    "request_id": envelope.request_id,
                },
            )
            # Future: dispatch to restaurant order domain pipeline / state machine
            return event

        logger.info(
            "Ignored unsupported event '%s' from user %s",
            event.event_name,
            event.user_id,
            extra={"event_name": event.event_name, "user_id": event.user_id},
        )
        return None
