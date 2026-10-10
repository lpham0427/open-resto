"""Base interface and types for provider-specific order handlers."""

from __future__ import annotations

from typing import Any, Protocol

from shared.envelope import EventEnvelope


class OrderHandler(Protocol):
    """Protocol for provider-specific order handlers.

    Why a Protocol?
    Enables structural typing so each provider handler (Zalo, Telegram, etc.)
    can be independently designed, tested, and implemented without inheriting
    from a rigid base class hierarchy.
    """

    def handle(self, envelope: EventEnvelope) -> Any:
        """Process an order event payload contained in the EventEnvelope.

        Returns:
            Domain event or processing result if successfully processed.
            None if safely discarded or ignored (poison pill, unsupported event).

        Raises:
            Exception: Transient errors that should trigger SQS retry.
        """
        ...
