"""Strict parser and field extractors for Zalo webhook payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from shared.zalo.models import (
    UnsupportedEvent,
    UserSendTextEvent,
    ZaloEvent,
    ZaloTextMessage,
)

MAX_FIELD_LENGTH = 256
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MAX_UNIX_MS = int(
    (datetime.max.replace(tzinfo=UTC) - _EPOCH) / timedelta(milliseconds=1)
)


class InvalidPayloadError(ValueError):
    """Raised when the raw payload is malformed or violates expected schema.

    Why a dedicated exception class?
    In SQS FIFO consumers, distinguishing between unrecoverable schema errors
    (poison pills) and transient failures (network/database timeouts) is critical:
    - Poison pills should be discarded or sent to DLQ without blocking the FIFO queue.
    - Transient failures should be reported in batchItemFailures for automatic
      SQS retry.
    """


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys.

    `json.loads` silently keeps the last duplicate, which lets two parsers
    disagree about the same payload (parser differential attacks).
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _get_bounded_string(payload: Mapping[str, Any], key: str) -> str | None:
    """Extract string value bounded within [1, MAX_FIELD_LENGTH]."""
    value = payload.get(key)
    if isinstance(value, str) and 0 < len(value) <= MAX_FIELD_LENGTH:
        return value
    return None


def parse_timestamp(timestamp: str) -> datetime | None:
    """Parse a positive Unix timestamp in milliseconds made of ASCII digits only."""
    # str.isdigit() also accepts non-ASCII digits, so isascii() is required.
    if not (timestamp.isascii() and timestamp.isdigit()):
        return None
    milliseconds = int(timestamp)
    if milliseconds <= 0 or milliseconds > _MAX_UNIX_MS:
        return None
    try:
        return _EPOCH + timedelta(milliseconds=milliseconds)
    except OverflowError:
        return None


def extract_user_id(payload: Mapping[str, Any]) -> str | None:
    """Extract bounded user ID from sender.id or user_id_by_app."""
    sender_obj = payload.get("sender")
    if isinstance(sender_obj, Mapping):
        sender_id = sender_obj.get("id")
        if isinstance(sender_id, str) and 0 < len(sender_id) <= MAX_FIELD_LENGTH:
            return sender_id.strip() or None
        if isinstance(sender_id, int) and sender_id > 0:
            return str(sender_id)

    user_id_by_app = payload.get("user_id_by_app")
    if isinstance(user_id_by_app, str) and 0 < len(user_id_by_app) <= MAX_FIELD_LENGTH:
        return user_id_by_app.strip() or None
    if isinstance(user_id_by_app, int) and user_id_by_app > 0:
        return str(user_id_by_app)

    return None


def extract_msg_id(payload: Mapping[str, Any]) -> str | None:
    """Extract optional bounded message ID from message.msg_id for deduplication."""
    msg_obj = payload.get("message")
    if isinstance(msg_obj, Mapping):
        raw_msg_id = msg_obj.get("msg_id")
        if isinstance(raw_msg_id, str) and 0 < len(raw_msg_id) <= MAX_FIELD_LENGTH:
            return raw_msg_id.strip() or None
        if isinstance(raw_msg_id, int) and raw_msg_id > 0:
            return str(raw_msg_id)
    return None


def parse_zalo_event(raw_payload: str, occurred_at_utc: str | None = None) -> ZaloEvent:
    """Parse raw JSON string into a strongly-typed ZaloEvent instance.

    Raises:
        InvalidPayloadError: If JSON is malformed or mandatory fields are missing.
    """
    try:
        data = json.loads(raw_payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError, TypeError, RecursionError) as err:
        raise InvalidPayloadError(f"Malformed JSON in raw_payload: {err}") from err

    if not isinstance(data, dict):
        raise InvalidPayloadError(
            f"Payload must be a JSON object, got {type(data).__name__}"
        )

    event_name = data.get("event_name")
    if not isinstance(event_name, str) or not event_name.strip():
        raise InvalidPayloadError("Missing or invalid 'event_name' field")

    app_id = data.get("app_id")
    app_id_str = str(app_id).strip() if app_id is not None else ""

    user_id = extract_user_id(data)

    # Route based on event type
    if event_name == "user_send_text":
        if not user_id:
            raise InvalidPayloadError(
                "Missing 'sender.id' or 'user_id_by_app' in user_send_text event"
            )

        if not app_id_str:
            raise InvalidPayloadError("Missing 'app_id' in user_send_text event")

        message_obj = data.get("message")
        if not isinstance(message_obj, Mapping):
            raise InvalidPayloadError("Missing or invalid 'message' object")

        text = message_obj.get("text")
        if not isinstance(text, str):
            raise InvalidPayloadError("Missing or invalid 'message.text' string")

        msg_id = extract_msg_id(data)
        if not msg_id:
            raw_msg_id = message_obj.get("msg_id")
            if raw_msg_id is None:
                raise InvalidPayloadError("Missing 'message.msg_id'")
            raise InvalidPayloadError("'message.msg_id' cannot be empty")

        raw_ts = data.get("timestamp")
        try:
            timestamp_ms = int(raw_ts) if raw_ts is not None else 0
        except (ValueError, TypeError) as err:
            raise InvalidPayloadError(f"Invalid 'timestamp' value: {raw_ts}") from err

        recipient_obj = data.get("recipient")
        recipient_id = ""
        if isinstance(recipient_obj, Mapping) and recipient_obj.get("id") is not None:
            recipient_id = str(recipient_obj.get("id"))

        user_id_by_app = data.get("user_id_by_app")
        user_id_by_app_str = (
            str(user_id_by_app).strip() if user_id_by_app is not None else None
        )

        return UserSendTextEvent(
            app_id=app_id_str,
            user_id=user_id,
            recipient_id=recipient_id,
            message=ZaloTextMessage(msg_id=msg_id, text=text),
            timestamp_ms=timestamp_ms,
            occurred_at_utc=occurred_at_utc,
            user_id_by_app=user_id_by_app_str,
        )

    # Known or unknown event types not yet processed as orders
    return UnsupportedEvent(
        event_name=event_name,
        user_id=user_id,
        app_id=app_id_str or None,
    )
