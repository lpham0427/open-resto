"""Envelope model for packaging verified external events into SQS."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


def _require_str(data: dict[str, Any], key: str) -> str:
    # Why strict validation instead of str(data[key])?
    # Using str(data[key]) silently corrupts data: e.g. str(None) becomes "None",
    # and str(dict) becomes a Python string representation with single quotes
    # ("{'a': 1}") which is invalid JSON. raw_payload must preserve the exact
    # string bytes without silent corruption, so non-string types must raise.
    if key not in data:
        raise ValueError(f"Missing required field: '{key}'")
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"Field '{key}' must be a string, got {type(value).__name__}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"Field '{key}' must be a string or None, got {type(value).__name__}"
        )
    return value


def _optional_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key)
    if value is None:
        return default
    # Note: bool is a subclass of int in Python (isinstance(True, int) is True).
    # Explicitly disallow bool so True is not mistakenly accepted as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"Field '{key}' must be an integer, got {type(value).__name__}"
        )
    return value


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Standardized envelope wrapping external events with ingestion metadata."""

    source: str
    request_id: str
    occurred_at_utc: str | None
    raw_payload: str

    # Why schema_version: int = 1?
    # Producer (receive_zalo_event) and consumer (process_order) share this module
    # but deploy independently (rolling deployments). Furthermore, messages can sit
    # in SQS queues or DLQs for up to 14 days before being processed.
    # An explicit schema_version allows consumer code to branch or migrate legacy
    # envelope shapes safely when fields are modified in future versions without
    # breaking in-flight messages.
    schema_version: int = 1

    def to_json(self) -> str:
        """Serialize envelope to JSON string for SQS MessageBody."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> EventEnvelope:
        """Deserialize JSON string into EventEnvelope with strict type checks."""
        data: dict[str, Any] = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(
                f"Envelope JSON must be an object, got {type(data).__name__}"
            )

        source_val = data.get("source")
        if source_val is not None and not isinstance(source_val, str):
            err_type = type(source_val).__name__
            raise ValueError(
                f"Field 'source' must be a string or omitted, got {err_type}"
            )
        source = source_val or "zalo"

        return cls(
            source=source,
            request_id=_require_str(data, "request_id"),
            occurred_at_utc=_optional_str(data, "occurred_at_utc"),
            raw_payload=_require_str(data, "raw_payload"),
            schema_version=_optional_int(data, "schema_version", default=1),
        )

    @classmethod
    def create(
        cls,
        source: str,
        request_id: str,
        occurred_at: datetime | None,
        raw_payload: str,
        schema_version: int = 1,
    ) -> EventEnvelope:
        """Factory constructor converting datetime objects to UTC ISO strings."""
        occurred_at_utc: str | None = None
        if occurred_at is not None:
            # Why normalize UTC and reject naive datetime?
            # 1. If a naive datetime is passed, it has no offset and creates ambiguity.
            # 2. If a localized datetime (e.g. +07:00) is passed, dt.isoformat() retains
            #    the non-UTC offset. Converting via dt.astimezone(UTC) ensures the field
            #    strictly lives up to its name ('_utc') and is always stored in standard
            #    UTC with offset +00:00 (e.g. '2026-10-10T11:00:00+00:00').
            if occurred_at.tzinfo is None:
                raise ValueError(
                    "occurred_at must be timezone-aware (got naive datetime: "
                    f"{occurred_at})"
                )
            occurred_at_utc = occurred_at.astimezone(UTC).isoformat()

        return cls(
            source=source,
            request_id=request_id,
            occurred_at_utc=occurred_at_utc,
            raw_payload=raw_payload,
            schema_version=schema_version,
        )


# Backward-compatible alias for existing imports
ZaloWebhookEnvelope = EventEnvelope
