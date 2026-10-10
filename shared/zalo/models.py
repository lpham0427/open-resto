"""Domain and event models for Zalo Official Account events."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ZaloTextMessage:
    """Represents text content within a Zalo message event."""

    msg_id: str
    text: str


@dataclass(frozen=True, slots=True)
class UserSendTextEvent:
    """Domain event representing a text message sent by a customer to the OA.

    Why this model?
    Decouples raw Zalo JSON structures from internal business logic.
    Provides immutable, type-safe access to order intake messages.
    """

    app_id: str
    user_id: str
    recipient_id: str
    message: ZaloTextMessage
    timestamp_ms: int
    occurred_at_utc: str | None = None
    user_id_by_app: str | None = None


@dataclass(frozen=True, slots=True)
class UnsupportedEvent:
    """Represents a valid Zalo event that is not yet handled (e.g. stickers, audio).

    Why this model?
    Allows the worker to recognize non-order events and acknowledge them
    without raising unexpected errors or blocking the SQS FIFO queue.
    """

    event_name: str
    user_id: str | None = None
    app_id: str | None = None


# Discriminated union of parsed Zalo events
type ZaloEvent = UserSendTextEvent | UnsupportedEvent
