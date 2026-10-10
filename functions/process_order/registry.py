"""Central registry and decorator for order source handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from process_order.handlers.base import OrderHandler

T = TypeVar("T", bound=OrderHandler)

_REGISTRY: dict[str, type[OrderHandler]] = {}


def register_order_handler(source: str) -> Callable[[type[T]], type[T]]:
    """Decorator to auto-register an OrderHandler class for a given source.

    Why this decorator?
    Eliminates manual registration code. Each handler module declares its
    own source binding directly above the class definition.

    Example:
        @register_order_handler("zalo")
        class ZaloOrderHandler:
            ...
    """
    normalized = source.strip().lower()

    def decorator(cls: type[T]) -> type[T]:
        _REGISTRY[normalized] = cls
        return cls

    return decorator


def get_registered_handler(source: str) -> type[OrderHandler] | None:
    """Look up a registered handler class by source identifier."""
    return _REGISTRY.get(source.strip().lower())


def list_registered_sources() -> list[str]:
    """List all currently registered source identifiers."""
    return list(_REGISTRY.keys())


def clear_registry() -> None:
    """Clear the registry (used primarily in test teardown)."""
    _REGISTRY.clear()
