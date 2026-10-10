"""HTTP entry point for Zalo Webhook on AWS Lambda Function URL."""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from typing import Any

from shared.envelope import ZaloWebhookEnvelope

from .freshness import WebhookFreshnessStatus, evaluate_freshness
from .parser import parse_candidate
from .settings import (
    get_events_queue_url,
    get_oa_secret_key,
    get_sqs_client,
    get_zalo_app_id,
)
from .signature import verify_signature

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SQS_GRACE_PERIOD_MS = 500.0


def _get_remaining_ms(context: Any) -> float | None:
    """Safely extract remaining execution time in milliseconds from Lambda context."""
    if context and hasattr(context, "get_remaining_time_in_millis"):
        try:
            return float(context.get_remaining_time_in_millis())
        except Exception:
            return None
    return None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process incoming Zalo Webhook requests.

    1. Strict parsing & structural validation (duplicate-key rejection, bounded fields).
    2. Cryptographic signature verification using X-ZEvent-Signature.
    3. Freshness evaluation to prevent replay attacks and handle clock skew.
    4. Fail-fast timeout check (500ms safety buffer before AWS hard kill).
    5. Packaging into ZaloWebhookEnvelope and enqueuing to SQS FIFO queue with
       bounded latency.
    6. Return 200 OK within Zalo's SLA.
    """
    received_at_utc = datetime.now(tz=UTC)
    remaining_ms = _get_remaining_ms(context)
    logger.info("Start webhook execution. RemainingTimeMs: %s", remaining_ms)

    request_context = event.get("requestContext", {})
    request_id = str(request_context.get("requestId") or "unknown-request-id")

    # Step: extract raw body
    raw_body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        try:
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        except Exception:
            logger.warning("Failed to decode base64 body. RequestId: %s", request_id)
            return {"statusCode": 400}

    if not raw_body:
        return {"statusCode": 400}

    # Step: parse & validate candidate (header keys normalized to lowercase)
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    candidate, validation_errors = parse_candidate(headers, raw_body)

    if validation_errors or candidate is None:
        flat_errors = "; ".join(
            f"{k}: {', '.join(v)}" for k, v in validation_errors.items()
        )
        logger.warning(
            "Can't parse Zalo webhook candidate. Errors: %s. RequestId: %s",
            flat_errors,
            request_id,
        )
        return {"statusCode": 400}

    # Step: verify signature against trusted configured app_id
    trusted_app_id = get_zalo_app_id()
    try:
        oa_secret_key = get_oa_secret_key()
    except Exception:
        logger.exception(
            "Failed to retrieve Zalo OA secret key from SSM. RequestId: %s",
            request_id,
        )
        return {"statusCode": 500}

    if not verify_signature(
        claimed_app_id=candidate.app_id,
        trusted_app_id=trusted_app_id,
        raw_body=raw_body,
        timestamp=candidate.timestamp,
        secret_key=oa_secret_key,
        signature=candidate.signature,
    ):
        logger.warning("Rejected: invalid signature. RequestId: %s", request_id)
        return {"statusCode": 401}

    # Step: freshness evaluation (replay protection and clock skew)
    freshness_status = evaluate_freshness(
        candidate.occurred_at, now_utc=received_at_utc
    )
    if freshness_status == WebhookFreshnessStatus.EXPIRED:
        # An expired event can never become fresh again. Acknowledge with 200 OK
        # so Zalo does not endlessly retry a request that will always be rejected.
        logger.info(
            "Event expired (%s). Acknowledged with 200 OK. RequestId: %s",
            candidate.timestamp,
            request_id,
        )
        return {"statusCode": 200}

    if freshness_status == WebhookFreshnessStatus.FUTURE_DATED:
        # Treat clock skew as a transient error; 503 forces Zalo redelivery.
        logger.warning(
            "Event future-dated (%s). Returning 503. RequestId: %s",
            candidate.timestamp,
            request_id,
        )
        return {"statusCode": 503}

    # Step: fail-fast timeout check (500ms safety buffer before hard kill)
    current_remaining_ms = _get_remaining_ms(context)
    if current_remaining_ms is not None and current_remaining_ms <= SQS_GRACE_PERIOD_MS:
        logger.warning(
            "Execution time remaining too low (%sms <= %sms). Failing fast.",
            current_remaining_ms,
            SQS_GRACE_PERIOD_MS,
        )
        return {"statusCode": 503}

    # Step: enqueue envelope to SQS
    queue_url = get_events_queue_url()
    if not queue_url:
        logger.error("EVENTS_QUEUE_URL is not set. RequestId: %s", request_id)
        return {"statusCode": 500}

    envelope = ZaloWebhookEnvelope.create(
        request_id=request_id,
        received_at=received_at_utc,
        occurred_at=candidate.occurred_at,
        raw_payload=raw_body,
    )
    envelope_json = envelope.to_json()

    try:
        sqs_client = get_sqs_client()
        send_params: dict[str, Any] = {
            "QueueUrl": queue_url,
            "MessageBody": envelope_json,
            "MessageAttributes": {
                "event_name": {
                    "DataType": "String",
                    "StringValue": candidate.event_name,
                },
                "app_id": {
                    "DataType": "String",
                    "StringValue": candidate.app_id,
                },
            },
        }
        if queue_url.endswith(".fifo"):
            send_params["MessageGroupId"] = candidate.user_id
            if candidate.msg_id:
                send_params["MessageDeduplicationId"] = candidate.msg_id

        sqs_client.send_message(**send_params)
    except Exception:
        # Log exception stack trace but omit raw_body to avoid leaking PII/tokens
        logger.exception(
            "Failed to send message to SQS queue. RequestId: %s", request_id
        )
        return {"statusCode": 503}

    logger.info(
        "Successfully enqueued event: %s. RequestId: %s",
        candidate.event_name,
        request_id,
    )
    return {"statusCode": 200}
