"""Runtime configuration loaded from environment variables and AWS SSM."""

from __future__ import annotations

import functools
import os
from typing import Any

import boto3
from botocore.config import Config

_cached_secret: str | None = None


def get_zalo_app_id() -> str:
    """Return the configured Zalo App ID."""
    return os.environ.get("ZALO_APP_ID", "")


def get_oa_secret_key_param_name() -> str:
    """Return the SSM parameter name for Zalo OA Secret Key."""
    return os.environ.get(
        "ZALO_OA_SECRET_KEY_PARAMETER", "/open-resto/zalo/oa-secret-key"
    )


def get_events_queue_url() -> str:
    """Return the SQS queue URL for incoming order events."""
    return os.environ.get("EVENTS_QUEUE_URL", "")


@functools.lru_cache(maxsize=1)
def get_ssm_client() -> Any:
    """Return a cached boto3 SSM client."""
    return boto3.client("ssm")


@functools.lru_cache(maxsize=1)
def get_sqs_client() -> Any:
    """Return a cached boto3 SQS client with bounded latency.

    Zalo expects a response within 2 seconds. Boto3 client retries are disabled
    via total_max_attempts=1 (max_attempts in Config counts only retries, whereas
    total_max_attempts=1 enforces exactly 1 initial attempt with 0 retries).
    Worst-case latency is bounded to 0.5s connect + 1.0s read = 1.5s, allowing the
    handler to fail-fast with 503 before Zalo times out and avoiding duplicate
    message enqueuing if SQS received the message but the ACK was delayed.
    """
    return boto3.client(
        "sqs",
        config=Config(
            connect_timeout=0.5,
            read_timeout=1.0,
            retries={"total_max_attempts": 1, "mode": "standard"},
        ),
    )


def get_oa_secret_key(ssm_client: Any = None) -> str:
    """Fetch and cache the Zalo OA Secret Key from SSM Parameter Store.

    The secret is cached in memory across warm Lambda invocations so that
    subsequent requests do not incur an additional network call to SSM.
    """
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret

    client = ssm_client or get_ssm_client()
    param_name = get_oa_secret_key_param_name()
    response = client.get_parameter(Name=param_name, WithDecryption=True)
    _cached_secret = response["Parameter"]["Value"]
    return _cached_secret


def clear_secret_cache() -> None:
    """Clear the cached secret key (primarily used in tests)."""
    global _cached_secret
    _cached_secret = None
