"""Webhook freshness policy to protect against replay attacks and clock skew."""

import logging
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)

# Default policy thresholds
DEFAULT_MAX_AGE_SECONDS = 3600  # 1 hour max age for incoming events
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 60  # 60 seconds tolerance for clock skew


class WebhookFreshnessStatus(StrEnum):
    """Evaluation result for webhook event freshness."""

    FRESH = "FRESH"
    EXPIRED = "EXPIRED"
    FUTURE_DATED = "FUTURE_DATED"


def parse_timestamp_to_datetime(timestamp_raw: str | int | float) -> datetime | None:
    """Parse raw timestamp (seconds or milliseconds) into UTC datetime."""
    try:
        ts_val = float(timestamp_raw)
    except ValueError, TypeError:
        return None

    # Epoch milliseconds check (e.g. 13-digit timestamp > 1e11)
    if ts_val > 100_000_000_000:
        ts_val /= 1000.0

    try:
        return datetime.fromtimestamp(ts_val, tz=UTC)
    except OverflowError, OSError, ValueError:
        return None


def evaluate_freshness(
    timestamp_raw: str | int | float,
    now_utc: datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
) -> tuple[WebhookFreshnessStatus, datetime | None]:
    """Evaluate whether an event timestamp is fresh, expired, or future-dated.

    Returns:
        (WebhookFreshnessStatus, occurred_at_datetime)
    """
    occurred_at = parse_timestamp_to_datetime(timestamp_raw)
    if occurred_at is None:
        logger.warning("Unparseable webhook timestamp: %s", timestamp_raw)
        return WebhookFreshnessStatus.EXPIRED, None

    now = now_utc or datetime.now(tz=UTC)
    delta_seconds = (now - occurred_at).total_seconds()

    if delta_seconds > max_age_seconds:
        return WebhookFreshnessStatus.EXPIRED, occurred_at

    if delta_seconds < -max_future_skew_seconds:
        return WebhookFreshnessStatus.FUTURE_DATED, occurred_at

    return WebhookFreshnessStatus.FRESH, occurred_at
