"""HTTP entry point for Zalo Webhook on AWS Lambda Function URL."""

import base64
import json
import logging
from typing import Any

from api.signature import verify_signature
from shared.settings import (
    get_events_queue_url,
    get_oa_secret_key,
    get_sqs_client,
    get_zalo_app_id,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _response(status_code: int, body_data: dict[str, Any]) -> dict[str, Any]:
    """Helper to build standardized Lambda Function URL response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body_data),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process incoming Zalo Webhook requests.

    1. Verify HTTP method is POST.
    2. Extract and decode raw body.
    3. Parse payload for app_id and timestamp.
    4. Authenticate request using X-ZEvent-Signature.
    5. Enqueue valid events into SQS for asynchronous processing.
    6. Return 200 OK within Zalo's 2-second timeout window.
    """
    request_context = event.get("requestContext", {})
    http_info = request_context.get("http", {})
    method = http_info.get("method", "POST").upper()

    if method != "POST":
        logger.warning("Rejected non-POST method: %s", method)
        return _response(405, {"error": "Method Not Allowed"})

    # Extract raw body (preserve original formatting for signature verification)
    raw_body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        try:
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        except Exception:
            logger.warning("Failed to decode base64 body")
            return _response(400, {"error": "Invalid base64 payload"})

    if not raw_body:
        return _response(400, {"error": "Empty body"})

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON body")
        return _response(400, {"error": "Invalid JSON body"})

    if not isinstance(payload, dict):
        logger.warning("Payload is not a JSON object")
        return _response(400, {"error": "Invalid JSON body, expected object"})

    app_id = str(payload.get("app_id") or get_zalo_app_id())
    timestamp = str(payload.get("timestamp") or payload.get("timeStamp") or "")

    if not app_id or not timestamp:
        logger.warning("Missing app_id or timestamp in payload")
        return _response(400, {"error": "Missing app_id or timestamp"})

    # Extract signature header (case-insensitive lookup)
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature_header = headers.get("x-zevent-signature")

    try:
        oa_secret_key = get_oa_secret_key()
    except Exception:
        logger.exception("Failed to retrieve Zalo OA secret key from SSM")
        return _response(500, {"error": "Internal configuration error"})

    if not verify_signature(
        app_id, raw_body, timestamp, oa_secret_key, signature_header
    ):
        logger.warning("Invalid webhook signature for app_id: %s", app_id)
        return _response(401, {"error": "Invalid signature"})

    queue_url = get_events_queue_url()
    if not queue_url:
        logger.error("EVENTS_QUEUE_URL is not set")
        return _response(500, {"error": "Queue configuration error"})

    event_name = str(payload.get("event_name", "unknown"))

    try:
        sqs_client = get_sqs_client()
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=raw_body,
            MessageAttributes={
                "event_name": {"DataType": "String", "StringValue": event_name},
                "app_id": {"DataType": "String", "StringValue": app_id},
            },
        )
    except Exception:
        logger.exception("Failed to send message to SQS queue")
        return _response(500, {"error": "Failed to enqueue event"})

    logger.info(
        "Successfully enqueued Zalo event: %s for app_id: %s",
        event_name,
        app_id,
    )
    return _response(200, {"status": "ok"})
