"""Queue consumer entry point (placeholder)."""

from typing import Any


def lambda_handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Process incoming SQS messages containing Zalo events."""
    _ = (event, context)
    return {"batchItemFailures": []}
