"""Strict parsing and validation of incoming Zalo webhook requests.

Parsing only validates the *shape* of a request. The resulting candidate is
validated but NOT yet authenticated: it must still pass signature verification
before any of its data is trusted.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

MAX_FIELD_LENGTH = 256
SIGNATURE_HEADER = "x-zevent-signature"
SIGNATURE_PREFIX = "mac="

# A SHA-256 digest is exactly 32 bytes, i.e. 64 hexadecimal characters.
_SIGNATURE_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MAX_UNIX_MS = int(
    (datetime.max.replace(tzinfo=UTC) - _EPOCH) / timedelta(milliseconds=1)
)

type ValidationErrors = dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class WebhookCandidate:
    """Validated but not yet verified webhook data."""

    app_id: str
    signature: bytes
    timestamp: str  # Original text, used verbatim in the signature computation.
    occurred_at: datetime
    event_name: str
    user_id: str | None = None
    msg_id: str | None = None


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


def extract_signature(headers: Mapping[str, str]) -> bytes | None:
    """Extract the SHA-256 digest from the X-ZEvent-Signature header.

    `headers` keys MUST already be lowercase. AWS Lambda Function URLs use
    payload format 2.0, which always lowercases header names. Do not add
    case-insensitive matching here (YAGNI); normalize at the call site if a
    different event source is ever introduced.
    https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html#urls-payloads

    Duplicate headers arrive comma-joined (``mac=a,mac=b``); the strict
    64-hex-character check rejects them without any splitting logic.
    """
    raw = headers.get(SIGNATURE_HEADER)
    if raw is None:
        return None
    value = raw.removeprefix(SIGNATURE_PREFIX)
    if not _SIGNATURE_PATTERN.fullmatch(value):
        return None
    return bytes.fromhex(value)


def parse_candidate(
    headers: Mapping[str, str], raw_body: str
) -> tuple[WebhookCandidate | None, ValidationErrors]:
    """Validate the request shape and return a candidate or field-level errors."""
    try:
        payload = json.loads(raw_body, object_pairs_hook=_reject_duplicate_keys)
    except ValueError, RecursionError:
        return None, {
            "Payload": ["Payload must be JSON and have no duplicate properties."]
        }

    # Since RFC 8259 a JSON document may be any value, not only an object.
    if not isinstance(payload, dict):
        return None, {"Payload": ["Payload must contain exactly one JSON object."]}

    errors: ValidationErrors = {}

    app_id = _get_bounded_string(payload, "app_id")
    if app_id is None:
        errors["Payload.app_id"] = ["app_id must be a non-empty bounded string."]

    timestamp = _get_bounded_string(payload, "timestamp")
    occurred_at = parse_timestamp(timestamp) if timestamp is not None else None
    if occurred_at is None:
        errors["Payload.timestamp"] = [
            "timestamp must be a bounded string holding a positive Unix "
            "timestamp in milliseconds."
        ]

    signature = extract_signature(headers)
    if signature is None:
        errors[f"Headers.{SIGNATURE_HEADER}"] = [
            "Signature must be one 64-character hexadecimal SHA-256 digest, "
            "optionally prefixed by mac=."
        ]

    if (
        errors
        or app_id is None
        or timestamp is None
        or occurred_at is None
        or signature is None
    ):
        return None, errors

    event_name = _get_bounded_string(payload, "event_name") or "unknown"

    # Extract user identifier for FIFO grouping (sender.id or user_id_by_app)
    user_id: str | None = None
    sender_obj = payload.get("sender")
    if isinstance(sender_obj, Mapping):
        sender_id = sender_obj.get("id")
        if isinstance(sender_id, str | int):
            user_id = str(sender_id)
    if not user_id:
        user_id_by_app = payload.get("user_id_by_app")
        if isinstance(user_id_by_app, str | int):
            user_id = str(user_id_by_app)

    # Extract message identifier for FIFO message deduplication
    msg_id: str | None = None
    msg_obj = payload.get("message")
    if isinstance(msg_obj, Mapping):
        raw_msg_id = msg_obj.get("msg_id")
        if isinstance(raw_msg_id, str | int):
            msg_id = str(raw_msg_id)

    return WebhookCandidate(
        app_id=app_id,
        signature=signature,
        timestamp=timestamp,
        occurred_at=occurred_at,
        event_name=event_name,
        user_id=user_id,
        msg_id=msg_id,
    ), {}
