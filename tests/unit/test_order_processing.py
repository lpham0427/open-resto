"""Unit tests for process_order Lambda handler, factory, and shared Zalo models."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from shared.envelope import EventEnvelope
from shared.zalo.models import UnsupportedEvent, UserSendTextEvent
from shared.zalo.parser import InvalidPayloadError, parse_zalo_event

from process_order.app import lambda_handler
from process_order.factory import OrderHandlerFactory, UnsupportedSourceError
from process_order.handlers.zalo import ZaloOrderHandler
from process_order.registry import register_order_handler


@dataclass
class _DummyLambdaContext:
    function_name: str = "process_order"
    memory_limit_in_mb: int = 256
    invoked_function_arn: str = (
        "arn:aws:lambda:ap-southeast-1:123456789012:function:process_order"
    )
    aws_request_id: str = "test-request-id"


def _sample_valid_text_payload() -> str:
    return json.dumps(
        {
            "app_id": "360846524940903967",
            "timestamp": "1728000000000",
            "event_name": "user_send_text",
            "sender": {"id": "246845883529197922"},
            "user_id_by_app": "552177279717587730",
            "recipient": {"id": "112233445566"},
            "message": {
                "text": "Cho mình đặt 2 suất cơm gà",
                "msg_id": "96d3cdf3af150460909",
            },
        }
    )


# ---------------------------------------------------------------------------
# Envelope Contract Tests
# ---------------------------------------------------------------------------


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


def test_envelope_from_json_strict_type_validation() -> None:
    with pytest.raises(ValueError, match="Envelope JSON must be an object"):
        EventEnvelope.from_json("[]")

    with pytest.raises(ValueError, match="Missing required field: 'source'"):
        EventEnvelope.from_json('{"request_id":"req-1","raw_payload":"{}"}')

    with pytest.raises(ValueError, match="Field 'source' must be a string"):
        EventEnvelope.from_json(
            '{"source":123,"request_id":"req-1","raw_payload":"{}"}'
        )

    with pytest.raises(ValueError, match="Missing required field: 'request_id'"):
        EventEnvelope.from_json('{"source":"zalo","raw_payload":"{}"}')

    with pytest.raises(ValueError, match="Missing required field: 'raw_payload'"):
        EventEnvelope.from_json('{"source":"zalo","request_id":"req-1"}')

    with pytest.raises(ValueError, match="Field 'raw_payload' must be a string"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":{"a":1}}'
        )

    with pytest.raises(ValueError, match="Field 'raw_payload' must be a string"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":null}'
        )

    with pytest.raises(ValueError, match="Field 'request_id' must be a string"):
        EventEnvelope.from_json('{"source":"zalo","request_id":123,"raw_payload":"{}"}')

    with pytest.raises(ValueError, match="Field 'occurred_at_utc' must be a string"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":"{}","occurred_at_utc":123}'
        )

    with pytest.raises(ValueError, match="Field 'schema_version' must be an integer"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":"{}","schema_version":"1"}'
        )

    with pytest.raises(ValueError, match="Field 'schema_version' must be an integer"):
        EventEnvelope.from_json(
            '{"source":"zalo","request_id":"req-1","raw_payload":"{}","schema_version":true}'
        )


def test_envelope_create_timezone_handling() -> None:
    naive_dt = datetime(2026, 10, 10, 12, 0, 0)
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        EventEnvelope.create(
            source="zalo",
            request_id="req-1",
            occurred_at=naive_dt,
            raw_payload="{}",
        )

    tz_vietnam = timezone(timedelta(hours=7))
    local_dt = datetime(2026, 10, 10, 18, 0, 0, tzinfo=tz_vietnam)
    env = EventEnvelope.create(
        source="zalo",
        request_id="req-1",
        occurred_at=local_dt,
        raw_payload="{}",
    )
    assert env.occurred_at_utc == "2026-10-10T11:00:00+00:00"

    env_none = EventEnvelope.create(
        source="zalo",
        request_id="req-1",
        occurred_at=None,
        raw_payload="{}",
    )
    assert env_none.occurred_at_utc is None


# ---------------------------------------------------------------------------
# Shared Zalo Event Parser Tests
# ---------------------------------------------------------------------------


def test_parse_valid_user_send_text_event() -> None:
    raw_payload = _sample_valid_text_payload()
    event = parse_zalo_event(raw_payload, occurred_at_utc="2026-10-10T11:00:00+00:00")

    assert isinstance(event, UserSendTextEvent)
    assert event.app_id == "360846524940903967"
    assert event.user_id == "246845883529197922"
    assert event.recipient_id == "112233445566"
    assert event.user_id_by_app == "552177279717587730"
    assert event.timestamp_ms == 1728000000000
    assert event.occurred_at_utc == "2026-10-10T11:00:00+00:00"
    assert event.message.msg_id == "96d3cdf3af150460909"
    assert event.message.text == "Cho mình đặt 2 suất cơm gà"

    # Verify immutability
    with pytest.raises(FrozenInstanceError):
        event.user_id = "mutated"

    with pytest.raises(FrozenInstanceError):
        event.message.text = "mutated"


def test_parse_user_send_text_fallback_to_user_id_by_app() -> None:
    raw_payload = json.dumps(
        {
            "app_id": "360846524940903967",
            "timestamp": 1728000000000,
            "event_name": "user_send_text",
            "user_id_by_app": "app-user-999",
            "message": {
                "text": "Menu hôm nay có gì?",
                "msg_id": "msg-001",
            },
        }
    )
    event = parse_zalo_event(raw_payload)

    assert isinstance(event, UserSendTextEvent)
    assert event.user_id == "app-user-999"
    assert event.user_id_by_app == "app-user-999"
    assert event.recipient_id == ""


def test_parse_unsupported_event() -> None:
    raw_payload = json.dumps(
        {
            "app_id": "360846524940903967",
            "timestamp": "1728000000000",
            "event_name": "user_send_image",
            "sender": {"id": "user-photo-1"},
        }
    )
    event = parse_zalo_event(raw_payload)

    assert isinstance(event, UnsupportedEvent)
    assert event.event_name == "user_send_image"
    assert event.user_id == "user-photo-1"
    assert event.app_id == "360846524940903967"


@pytest.mark.parametrize(
    ("bad_payload", "error_substring"),
    [
        ("{malformed-json", "Malformed JSON"),
        ("12345", "Payload must be a JSON object"),
        ("[]", "Payload must be a JSON object"),
        (
            '{"timestamp": 123}',
            "Missing or invalid 'event_name' field",
        ),
        (
            '{"event_name": "  "}',
            "Missing or invalid 'event_name' field",
        ),
        (
            '{"event_name": "user_send_text", "app_id": "123"}',
            "Missing 'sender.id' or 'user_id_by_app'",
        ),
        (
            '{"event_name": "user_send_text", "sender": {"id": "u1"}}',
            "Missing 'app_id'",
        ),
        (
            json.dumps(
                {
                    "event_name": "user_send_text",
                    "app_id": "123",
                    "sender": {"id": "u1"},
                }
            ),
            "Missing or invalid 'message' object",
        ),
        (
            json.dumps(
                {
                    "event_name": "user_send_text",
                    "app_id": "123",
                    "sender": {"id": "u1"},
                    "message": {"msg_id": "m1"},
                }
            ),
            "Missing or invalid 'message.text'",
        ),
        (
            json.dumps(
                {
                    "event_name": "user_send_text",
                    "app_id": "123",
                    "sender": {"id": "u1"},
                    "message": {"text": "hi"},
                }
            ),
            "Missing 'message.msg_id'",
        ),
        (
            json.dumps(
                {
                    "event_name": "user_send_text",
                    "app_id": "123",
                    "sender": {"id": "u1"},
                    "message": {"msg_id": "  ", "text": "hi"},
                }
            ),
            "'message.msg_id' cannot be empty",
        ),
        (
            json.dumps(
                {
                    "event_name": "user_send_text",
                    "app_id": "123",
                    "sender": {"id": "u1"},
                    "message": {"msg_id": "m1", "text": "hi"},
                    "timestamp": "not-numeric",
                }
            ),
            "Invalid 'timestamp' value",
        ),
    ],
)
def test_parse_invalid_payload_raises_invalid_payload_error(
    bad_payload: str, error_substring: str
) -> None:
    with pytest.raises(InvalidPayloadError, match=error_substring):
        parse_zalo_event(bad_payload)


# ---------------------------------------------------------------------------
# Order Handler Factory Tests
# ---------------------------------------------------------------------------


def test_order_handler_factory_resolves_zalo_handler() -> None:
    handler = OrderHandlerFactory.get_handler("zalo")
    assert isinstance(handler, ZaloOrderHandler)

    # Verify case-insensitivity and whitespace stripping
    assert isinstance(OrderHandlerFactory.get_handler("  ZALO  "), ZaloOrderHandler)


def test_order_handler_factory_raises_for_unsupported_source() -> None:
    with pytest.raises(
        UnsupportedSourceError,
        match="No order handler registered for source 'unknown_provider'",
    ):
        OrderHandlerFactory.get_handler("unknown_provider")


def test_order_handler_factory_decorator_registration() -> None:
    @register_order_handler("telegram")
    class _MockTelegramHandler:
        def handle(self, envelope: EventEnvelope) -> str:
            return f"handled telegram: {envelope.request_id}"

    try:
        handler = OrderHandlerFactory.get_handler("telegram")
        assert isinstance(handler, _MockTelegramHandler)

        env = EventEnvelope.create(
            source="telegram",
            request_id="tg-123",
            occurred_at=datetime.now(tz=UTC),
            raw_payload="{}",
        )
        assert handler.handle(env) == "handled telegram: tg-123"
    finally:
        OrderHandlerFactory.reset_registry()


# ---------------------------------------------------------------------------
# Process Order Lambda Handler Integration Tests
# ---------------------------------------------------------------------------


def test_process_order_success() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="zalo",
        request_id="req-test-1",
        occurred_at=now,
        raw_payload=_sample_valid_text_payload(),
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


def test_process_order_unsupported_source_discarded() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="unregistered_provider",
        request_id="req-unknown-source",
        occurred_at=now,
        raw_payload="{}",
    )

    event: dict[str, Any] = {
        "Records": [
            {
                "messageId": "msg-unsupported-001",
                "body": envelope.to_json(),
                "eventSource": "aws:sqs",
            }
        ]
    }

    result = lambda_handler(event, _DummyLambdaContext())
    # Should safely drop/acknowledge without blocking FIFO queue
    assert result == {"batchItemFailures": []}


def test_process_order_unsupported_event_acknowledged() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="zalo",
        request_id="req-test-unsupported",
        occurred_at=now,
        raw_payload=json.dumps(
            {
                "app_id": "360846524940903967",
                "timestamp": "1728000000000",
                "event_name": "user_send_sticker",
                "sender": {"id": "user-sticker-1"},
            }
        ),
    )

    event: dict[str, Any] = {
        "Records": [
            {
                "messageId": "msg-sticker-001",
                "body": envelope.to_json(),
                "eventSource": "aws:sqs",
            }
        ]
    }

    result = lambda_handler(event, _DummyLambdaContext())
    assert result == {"batchItemFailures": []}


def test_process_order_poison_pill_discarded_without_failure() -> None:
    now = datetime(2026, 10, 9, 15, 30, 0, tzinfo=UTC)
    envelope = EventEnvelope.create(
        source="zalo",
        request_id="req-test-poison-pill",
        occurred_at=now,
        raw_payload="invalid-json-content",
    )

    event: dict[str, Any] = {
        "Records": [
            {
                "messageId": "msg-poison-001",
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
        raw_payload=_sample_valid_text_payload(),
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
