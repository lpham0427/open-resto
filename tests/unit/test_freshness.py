"""Unit tests for webhook freshness policy."""

from datetime import UTC, datetime, timedelta

from api.freshness import (
    MAX_AGE,
    MAX_FUTURE_SKEW,
    WebhookFreshnessStatus,
    evaluate_freshness,
)


def test_evaluate_freshness_fresh_event() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    occurred_at = now - timedelta(minutes=10)

    status = evaluate_freshness(occurred_at, now_utc=now)
    assert status == WebhookFreshnessStatus.FRESH


def test_evaluate_freshness_expired_event() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    # Outside the 65-minute window
    occurred_at = now - MAX_AGE - timedelta(seconds=1)

    status = evaluate_freshness(occurred_at, now_utc=now)
    assert status == WebhookFreshnessStatus.EXPIRED


def test_evaluate_freshness_future_dated_event() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    # Beyond the 1-day clock skew window
    occurred_at = now + MAX_FUTURE_SKEW + timedelta(seconds=1)

    status = evaluate_freshness(occurred_at, now_utc=now)
    assert status == WebhookFreshnessStatus.FUTURE_DATED
