"""Smoke test: every Lambda package and the shared package can be imported."""

import api.app
import shared.settings
import tokens.app
import worker.app


def test_packages_are_importable() -> None:
    for module in (api.app, worker.app, tokens.app, shared.settings):
        assert module.__doc__, f"{module.__name__} has no module docstring"
