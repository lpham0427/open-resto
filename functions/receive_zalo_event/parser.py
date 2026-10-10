"""Strict parsing and validation of incoming Zalo webhook requests.

Parsing only validates the *shape* of a request. The resulting candidate is
validated but NOT yet authenticated: it must still pass signature verification
before any of its data is trusted.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from shared.zalo.parser import (
    _get_bounded_string,
    _reject_duplicate_keys,
    extract_msg_id,
    extract_user_id,
    parse_timestamp,
)

__all__ = [
    "SIGNATURE_HEADER",
    "SIGNATURE_PREFIX",
    "ValidationErrors",
    "WebhookCandidate",
    "extract_signature",
    "parse_candidate",
    "parse_timestamp",
]

SIGNATURE_HEADER = "x-zevent-signature"
SIGNATURE_PREFIX = "mac="

# A SHA-256 digest is exactly 32 bytes, i.e. 64 hexadecimal characters.
_SIGNATURE_PATTERN = re.compile(r"[0-9a-fA-F]{64}")

type ValidationErrors = dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class WebhookCandidate:
    """Validated but not yet verified webhook data."""

    app_id: str
    signature: bytes
    timestamp: str  # Original text, used verbatim in the signature computation.
    occurred_at: datetime
    event_name: str
    user_id: str
    msg_id: str | None = None


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

    user_id = extract_user_id(payload)
    if user_id is None:
        errors["Payload.user_id"] = [
            "user_id must be provided via sender.id or user_id_by_app."
        ]

    if (
        errors
        or app_id is None
        or timestamp is None
        or occurred_at is None
        or signature is None
        or user_id is None
    ):
        return None, errors

    event_name = _get_bounded_string(payload, "event_name") or "unknown"
    msg_id = extract_msg_id(payload)

    return WebhookCandidate(
        app_id=app_id,
        signature=signature,
        timestamp=timestamp,
        occurred_at=occurred_at,
        event_name=event_name,
        user_id=user_id,
        msg_id=msg_id,
    ), {}
