"""Factory resolving provider-specific order handlers using lazy imports."""

from __future__ import annotations

from process_order.handlers.base import OrderHandler


class UnsupportedSourceError(ValueError):
    """Raised when an EventEnvelope has an unsupported or unregistered source."""


class OrderHandlerFactory:
    """Factory resolving provider-specific OrderHandler using lazy imports.

    Why match/case with lazy imports?
    - True lazy import: each provider module is imported only when an event
      from that source arrives.
    - No dynamic string reflection: imports are explicit, type-safe, and
      support IDE jump-to-definition.
    - Cold start stays fast: unused provider SDKs are never loaded.
    """

    @staticmethod
    def get_handler(source: str) -> OrderHandler:
        """Lazily load and return the OrderHandler for the given source.

        Raises:
            UnsupportedSourceError: If no handler is implemented for the source.
        """
        match source.strip().lower():
            case "zalo":
                from process_order.handlers.zalo import ZaloOrderHandler

                return ZaloOrderHandler()

            case _:
                raise UnsupportedSourceError(
                    f"No order handler registered for source '{source}'"
                )
