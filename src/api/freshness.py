"""Webhook freshness policy to protect against replay attacks and clock skew."""

import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)

# Zalo redelivers failed events after 30s, 5m, 15m, 30m and 1h. The window must
# outlive the last retry (1h) or legitimate redeliveries would be discarded.
MAX_AGE = timedelta(minutes=65)
# Events dated further in the future than this are treated as clock skew.
MAX_FUTURE_SKEW = timedelta(days=1)


class WebhookFreshnessStatus(StrEnum):
    """Evaluation result for webhook event freshness."""

    FRESH = "FRESH"
    EXPIRED = "EXPIRED"
    FUTURE_DATED = "FUTURE_DATED"


def evaluate_freshness(
    occurred_at: datetime,
    now_utc: datetime | None = None,
    max_age: timedelta = MAX_AGE,
    max_future_skew: timedelta = MAX_FUTURE_SKEW,
) -> WebhookFreshnessStatus:
    """Classify an authenticated event timestamp as fresh, expired or future-dated."""
    now = now_utc or datetime.now(tz=UTC)

    if occurred_at < now - max_age:
        logger.warning(
            "Authenticated webhook expired. occurred_at=%s now=%s max_age=%s",
            occurred_at,
            now,
            max_age,
        )
        return WebhookFreshnessStatus.EXPIRED

    if occurred_at > now + max_future_skew:
        logger.warning(
            "Authenticated webhook is future-dated. occurred_at=%s now=%s skew=%s",
            occurred_at,
            now,
            max_future_skew,
        )
        return WebhookFreshnessStatus.FUTURE_DATED

    return WebhookFreshnessStatus.FRESH
