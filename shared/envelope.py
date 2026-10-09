"""Envelope model for packaging verified Zalo webhook events into SQS."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ZaloWebhookEnvelope:
    """Standardized envelope wrapping the raw Zalo event with ingestion metadata."""

    request_id: str
    received_at_utc: str
    occurred_at_utc: str | None
    raw_payload: str

    def to_json(self) -> str:
        """Serialize envelope to JSON string for SQS MessageBody."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> ZaloWebhookEnvelope:
        """Deserialize JSON string into ZaloWebhookEnvelope."""
        data: dict[str, Any] = json.loads(raw)
        return cls(
            request_id=str(data["request_id"]),
            received_at_utc=str(data["received_at_utc"]),
            occurred_at_utc=str(data["occurred_at_utc"])
            if data.get("occurred_at_utc")
            else None,
            raw_payload=str(data["raw_payload"]),
        )

    @classmethod
    def create(
        cls,
        request_id: str,
        received_at: datetime,
        occurred_at: datetime | None,
        raw_payload: str,
    ) -> ZaloWebhookEnvelope:
        """Factory constructor converting datetime objects to ISO 8601 strings."""
        return cls(
            request_id=request_id,
            received_at_utc=received_at.isoformat(),
            occurred_at_utc=occurred_at.isoformat() if occurred_at else None,
            raw_payload=raw_payload,
        )
