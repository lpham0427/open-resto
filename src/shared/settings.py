"""Runtime configuration loaded from environment variables and AWS SSM."""

from __future__ import annotations

import functools
import os
from typing import Any

import boto3

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
    """Return the SQS queue URL for incoming Zalo events."""
    return os.environ.get("EVENTS_QUEUE_URL", "")


@functools.lru_cache(maxsize=1)
def get_ssm_client() -> Any:
    """Return a cached boto3 SSM client."""
    return boto3.client("ssm")


@functools.lru_cache(maxsize=1)
def get_sqs_client() -> Any:
    """Return a cached boto3 SQS client."""
    return boto3.client("sqs")


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
