"""Smoke test: every Lambda package and the shared package can be imported."""

import shared.envelope

import process_order.app
import receive_zalo_event.app
import receive_zalo_event.settings
import refresh_token.app


def test_packages_are_importable() -> None:
    for module in (
        receive_zalo_event.app,
        receive_zalo_event.settings,
        process_order.app,
        refresh_token.app,
        shared.envelope,
    ):
        assert module.__doc__, f"{module.__name__} has no module docstring"
