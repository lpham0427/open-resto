"""Unit tests for webhook freshness policy."""

from datetime import UTC, datetime, timedelta

from api.freshness import (
    WebhookFreshnessStatus,
    evaluate_freshness,
    parse_timestamp_to_datetime,
)


def test_parse_timestamp_formats() -> None:
    # Seconds (10 digits)
    dt_sec = parse_timestamp_to_datetime("1700000000")
    assert dt_sec is not None
    assert dt_sec.year >= 2023

    # Milliseconds (13 digits)
    dt_ms = parse_timestamp_to_datetime("1700000000000")
    assert dt_ms is not None
    assert dt_ms == dt_sec

    # Invalid string
    assert parse_timestamp_to_datetime("invalid") is None
    assert parse_timestamp_to_datetime("") is None


def test_evaluate_freshness_fresh_event() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    event_time = now - timedelta(seconds=120)  # 2 minutes ago
    ts_str = str(int(event_time.timestamp() * 1000))

    status, occurred_at = evaluate_freshness(ts_str, now_utc=now)
    assert status == WebhookFreshnessStatus.FRESH
    assert occurred_at is not None
    assert occurred_at == event_time


def test_evaluate_freshness_expired_event() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    event_time = now - timedelta(hours=2)  # 2 hours ago (> default 1 hour)
    ts_str = str(int(event_time.timestamp() * 1000))

    status, occurred_at = evaluate_freshness(ts_str, now_utc=now)
    assert status == WebhookFreshnessStatus.EXPIRED
    assert occurred_at is not None


def test_evaluate_freshness_future_dated_event() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    event_time = now + timedelta(minutes=5)  # 5 minutes in future (> 60s tolerance)
    ts_str = str(int(event_time.timestamp() * 1000))

    status, occurred_at = evaluate_freshness(ts_str, now_utc=now)
    assert status == WebhookFreshnessStatus.FUTURE_DATED
    assert occurred_at is not None


def test_evaluate_freshness_unparseable_timestamp() -> None:
    now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    status, occurred_at = evaluate_freshness("bad-timestamp", now_utc=now)
    assert status == WebhookFreshnessStatus.EXPIRED
    assert occurred_at is None
