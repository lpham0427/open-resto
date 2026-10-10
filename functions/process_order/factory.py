"""Factory and auto-discovery for provider-specific order handlers."""

from __future__ import annotations

import importlib
import pkgutil

import process_order.handlers as handlers_pkg
from process_order.handlers.base import OrderHandler
from process_order.registry import (
    clear_registry,
    get_registered_handler,
)


class UnsupportedSourceError(ValueError):
    """Raised when an EventEnvelope has an unsupported or unregistered source."""


def discover_handlers() -> None:
    """Auto-discover and import all handler modules in the handlers package.

    Why auto-discovery?
    Iterates over the handlers/ package directory and imports each module.
    When a module is imported, its @register_order_handler decorator fires
    and registers the class into the central registry. Adding a new provider
    only requires dropping a new file in handlers/ with the decorator.
    """
    for _, module_name, _ in pkgutil.iter_modules(handlers_pkg.__path__):
        if not module_name.startswith("_") and module_name != "base":
            importlib.import_module(f"process_order.handlers.{module_name}")


class OrderHandlerFactory:
    """Factory resolving provider-specific OrderHandler from envelope source."""

    @classmethod
    def get_handler(cls, source: str) -> OrderHandler:
        """Resolve and instantiate the OrderHandler for the given source.

        Raises:
            UnsupportedSourceError: If no handler is registered for the source.
        """
        handler_cls = get_registered_handler(source)
        if handler_cls is None:
            raise UnsupportedSourceError(
                f"No order handler registered for source '{source}'"
            )
        return handler_cls()

    @classmethod
    def reset_registry(cls) -> None:
        """Reset and re-discover handlers (useful for test isolation)."""
        clear_registry()
        discover_handlers()


# Run auto-discovery on module load
discover_handlers()
