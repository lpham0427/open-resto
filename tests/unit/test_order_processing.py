"""Unit tests for process_order Lambda handler and shared envelope contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from shared.envelope import EventEnvelope

from process_order.app import lambda_handler


@dataclass
class _DummyLambdaContext:
    function_name: str = "process_order"
    memory_limit_in_mb: int = 256
    invoked_function_arn: str = (
        "arn:aws:lambda:ap-southeast-1:123456789012:function:process_order"
    )
    aws_request_id: str = "test-request-id"


def test_envelope_roundtrip() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="zalo",
        request_id="req-12345",
        occurred_at=now,
        raw_payload='{"event_name":"user_send_text"}',
    )

    serialized = envelope.to_json()
    deserialized = EventEnvelope.from_json(serialized)

    assert deserialized.source == "zalo"
    assert deserialized.request_id == "req-12345"
    assert deserialized.occurred_at_utc == now.isoformat()
    assert deserialized.raw_payload == '{"event_name":"user_send_text"}'
    assert deserialized.schema_version == 1


def test_process_order_success() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="zalo",
        request_id="req-test-1",
        occurred_at=now,
        raw_payload='{"event_name":"user_send_text","app_id":"123"}',
    )

    event: dict[str, Any] = {
        "Records": [
            {
                "messageId": "msg-001",
                "body": envelope.to_json(),
                "eventSource": "aws:sqs",
            }
        ]
    }

    result = lambda_handler(event, _DummyLambdaContext())
    assert result == {"batchItemFailures": []}


def test_process_order_partial_failure() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="zalo",
        request_id="req-good",
        occurred_at=now,
        raw_payload='{"event_name":"user_send_text"}',
    )

    event: dict[str, Any] = {
        "Records": [
            {
                "messageId": "msg-good",
                "body": envelope.to_json(),
                "eventSource": "aws:sqs",
            },
            {
                "messageId": "msg-corrupted",
                "body": "not-valid-json",
                "eventSource": "aws:sqs",
            },
        ]
    }

    result = lambda_handler(event, _DummyLambdaContext())
    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-corrupted"}]}


def test_envelope_from_json_strict_type_validation() -> None:
    # Non-object json
    with pytest.raises(ValueError, match="Envelope JSON must be an object"):
        EventEnvelope.from_json("[]")

    # Missing required field: source
    with pytest.raises(ValueError, match="Missing required field: 'source'"):
        EventEnvelope.from_json('{"request_id":"req-1","raw_payload":"{}"}')

    # Non-string source
    with pytest.raises(ValueError, match="Field 'source' must be a string"):
        EventEnvelope.from_json(
            '{"source":123,"request_id":"req-1","raw_payload":"{}"}'
        )

    # Missing required field: request_id
    with pytest.raises(ValueError, match="Missing required field: 'request_id'"):
        EventEnvelope.from_json('{"source":"zalo","raw_payload":"{}"}')

    # Missing required field: raw_payload
    with pytest.raises(ValueError, match="Missing required field: 'raw_payload'"):
        EventEnvelope.from_json('{"source":"zalo","request_id":"req-1"}')

    # Non-string raw_payload (silent corruption prevention)
    with pytest.raises(ValueError, match="Field 'raw_payload' must be a string"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":{"a":1}}'
        )

    with pytest.raises(ValueError, match="Field 'raw_payload' must be a string"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":null}'
        )

    # Non-string request_id
    with pytest.raises(ValueError, match="Field 'request_id' must be a string"):
        EventEnvelope.from_json('{"source":"zalo","request_id":123,"raw_payload":"{}"}')

    # Non-string occurred_at_utc
    with pytest.raises(ValueError, match="Field 'occurred_at_utc' must be a string"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":"{}","occurred_at_utc":123}'
        )

    # Invalid schema_version
    with pytest.raises(ValueError, match="Field 'schema_version' must be an integer"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":"{}","schema_version":"1"}'
        )

    with pytest.raises(ValueError, match="Field 'schema_version' must be an integer"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":"{}","schema_version":true}'
        )


def test_envelope_create_timezone_handling() -> None:
    # Naive datetime must be rejected
    naive_dt = datetime(2026, 10, 10, 12, 0, 0)
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        EventEnvelope.create(
            source="zalo",
            request_id="req-1",
            occurred_at=naive_dt,
            raw_payload="{}",
        )

    # Localized datetime (UTC+7) must be normalized to UTC (+00:00)
    tz_vietnam = timezone(timedelta(hours=7))
    local_dt = datetime(2026, 10, 10, 18, 0, 0, tzinfo=tz_vietnam)
    env = EventEnvelope.create(
        source="zalo",
        request_id="req-1",
        occurred_at=local_dt,
        raw_payload="{}",
    )
    assert env.occurred_at_utc == "2026-10-10T11:00:00+00:00"

    # None occurred_at produces None
    env_none = EventEnvelope.create(
        source="zalo",
        request_id="req-1",
        occurred_at=None,
        raw_payload="{}",
    )
    assert env_none.occurred_at_utc is None
