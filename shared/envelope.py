"""Envelope model for packaging verified external events into SQS."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Standardized envelope wrapping external events with ingestion metadata."""

    source: str
    request_id: str
    occurred_at_utc: str | None
    raw_payload: str
    schema_version: int = 1

    def to_json(self) -> str:
        """Serialize envelope to JSON string for SQS MessageBody."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> EventEnvelope:
        """Deserialize JSON string into EventEnvelope."""
        data: dict[str, Any] = json.loads(raw)
        return cls(
            source=str(data.get("source", "zalo")),
            request_id=str(data["request_id"]),
            occurred_at_utc=str(data["occurred_at_utc"])
            if data.get("occurred_at_utc")
            else None,
            raw_payload=str(data["raw_payload"]),
            schema_version=int(data.get("schema_version", 1)),
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
        """Factory constructor converting datetime objects to ISO 8601 strings."""
        return cls(
            source=source,
            request_id=request_id,
            occurred_at_utc=occurred_at.isoformat() if occurred_at else None,
            raw_payload=raw_payload,
            schema_version=schema_version,
        )


# Backward-compatible alias for existing imports
ZaloWebhookEnvelope = EventEnvelope
