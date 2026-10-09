"""Unit tests for process_order Lambda handler and shared envelope contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shared.envelope import ZaloWebhookEnvelope

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
    envelope = ZaloWebhookEnvelope.create(
        request_id="req-12345",
        received_at=now,
        occurred_at=now,
        raw_payload='{"event_name":"user_send_text"}',
    )

    serialized = envelope.to_json()
    deserialized = ZaloWebhookEnvelope.from_json(serialized)

    assert deserialized.request_id == "req-12345"
    assert deserialized.received_at_utc == now.isoformat()
    assert deserialized.occurred_at_utc == now.isoformat()
    assert deserialized.raw_payload == '{"event_name":"user_send_text"}'


def test_process_order_success() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = ZaloWebhookEnvelope.create(
        request_id="req-test-1",
        received_at=now,
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
    envelope = ZaloWebhookEnvelope.create(
        request_id="req-good",
        received_at=now,
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
