"""Unit and integration tests for Zalo webhook Lambda handler."""

import base64
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from receive_zalo_event.app import lambda_handler
from receive_zalo_event.settings import (
    clear_secret_cache,
    get_oa_secret_key,
    get_sqs_client,
    get_ssm_client,
)
from receive_zalo_event.signature import compute_signature

TEST_APP_ID = "360846524940903967"
TEST_SECRET_KEY = "test_oa_secret_key_123"  # noqa: S105
TEST_PARAM_NAME = "/open-resto/zalo/oa-secret-key"
TEST_REGION = "ap-southeast-1"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials and default test environment variables."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", TEST_REGION)
    monkeypatch.setenv("ZALO_APP_ID", TEST_APP_ID)
    monkeypatch.setenv("ZALO_OA_SECRET_KEY_PARAMETER", TEST_PARAM_NAME)
    clear_secret_cache()
    get_ssm_client.cache_clear()
    get_sqs_client.cache_clear()


@pytest.fixture
def test_infrastructure(aws_env: None):
    """Provision mocked SSM parameter and SQS queue using moto."""
    with mock_aws():
        ssm = boto3.client("ssm", region_name=TEST_REGION)
        ssm.put_parameter(
            Name=TEST_PARAM_NAME,
            Value=TEST_SECRET_KEY,
            Type="SecureString",
            Overwrite=True,
        )

        sqs = boto3.client("sqs", region_name=TEST_REGION)
        queue_res = sqs.create_queue(
            QueueName="test-zalo-events-queue.fifo",
            Attributes={
                "FifoQueue": "true",
                "ContentBasedDeduplication": "true",
            },
        )
        queue_url = queue_res["QueueUrl"]
        os.environ["EVENTS_QUEUE_URL"] = queue_url

        yield {"ssm": ssm, "sqs": sqs, "queue_url": queue_url}


def _make_fresh_payload(seconds_ago: int = 30) -> dict[str, Any]:
    event_time = datetime.now(tz=UTC) - timedelta(seconds=seconds_ago)
    timestamp_ms = str(int(event_time.timestamp() * 1000))
    return {
        "app_id": TEST_APP_ID,
        "sender": {"id": "246845883529197922"},
        "user_id_by_app": "552177279717587730",
        "recipient": {"id": "388613280878808645"},
        "event_name": "user_send_text",
        "message": {
            "text": "Cho mình đặt 2 suất cơm gà",
            "msg_id": "96d3cdf3af150460909",
        },
        "timestamp": timestamp_ms,
    }


def _build_furl_event(
    body: str,
    method: str = "POST",
    signature_header: str | None = None,
    is_base64: bool = False,
    request_id: str = "test-req-123",
) -> dict[str, Any]:
    headers = {"content-type": "application/json"}
    if signature_header is not None:
        headers["x-zevent-signature"] = signature_header

    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/",
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "requestId": request_id,
            "http": {
                "method": method,
                "path": "/",
                "protocol": "HTTP/1.1",
            },
        },
        "body": body,
        "isBase64Encoded": is_base64,
    }


def test_webhook_success_enqueues_envelope(
    test_infrastructure: dict[str, Any],
) -> None:
    sqs = test_infrastructure["sqs"]
    queue_url = test_infrastructure["queue_url"]

    payload = _make_fresh_payload()
    raw_body = json.dumps(payload, separators=(",", ":"))
    sig = compute_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    ).hex()

    event = _build_furl_event(
        body=raw_body,
        method="POST",
        signature_header=f"mac={sig}",
        request_id="req-abc-999",
    )

    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    body_data = json.loads(response["body"])
    assert body_data["status"] == "ok"
    assert body_data["message"] == "ACK"

    # Verify message in SQS is properly structured envelope
    messages = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        MessageAttributeNames=["All"],
        AttributeNames=["All"],
    ).get("Messages", [])

    assert len(messages) == 1
    received = messages[0]
    envelope_data = json.loads(received["Body"])
    assert envelope_data["request_id"] == "req-abc-999"
    assert envelope_data["raw_payload"] == raw_body
    assert "received_at_utc" in envelope_data
    assert envelope_data["occurred_at_utc"] is not None

    attrs = received["MessageAttributes"]
    assert attrs["event_name"]["StringValue"] == "user_send_text"
    assert attrs["app_id"]["StringValue"] == TEST_APP_ID

    sys_attrs = received.get("Attributes", {})
    assert sys_attrs.get("MessageGroupId") == "246845883529197922"
    assert sys_attrs.get("MessageDeduplicationId") == "96d3cdf3af150460909"


def test_webhook_base64_encoded_body(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_fresh_payload()
    raw_body = json.dumps(payload, separators=(",", ":"))
    sig = compute_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    ).hex()
    b64_body = base64.b64encode(raw_body.encode("utf-8")).decode("utf-8")

    event = _build_furl_event(
        body=b64_body,
        method="POST",
        signature_header=sig,
        is_base64=True,
    )

    response = lambda_handler(event, None)
    assert response["statusCode"] == 200


def test_webhook_method_not_allowed_includes_allow_header(
    test_infrastructure: dict[str, Any],
) -> None:
    event = _build_furl_event(body="{}", method="GET")
    response = lambda_handler(event, None)
    assert response["statusCode"] == 405
    assert response["headers"]["Allow"] == "POST"
    assert json.loads(response["body"])["error"] == "Method Not Allowed"


def test_webhook_expired_event_acknowledged_with_200(
    test_infrastructure: dict[str, Any],
) -> None:
    sqs = test_infrastructure["sqs"]
    queue_url = test_infrastructure["queue_url"]

    # 70 minutes ago (> 65 min threshold)
    payload = _make_fresh_payload(seconds_ago=70 * 60)
    raw_body = json.dumps(payload)
    sig = compute_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    ).hex()
    event = _build_furl_event(body=raw_body, method="POST", signature_header=sig)

    response = lambda_handler(event, None)
    # Must acknowledge with 200 so Zalo does not endlessly retry dead events
    assert response["statusCode"] == 200
    assert "Expired" in json.loads(response["body"])["message"]

    # SQS must not receive the expired event
    messages = sqs.receive_message(QueueUrl=queue_url).get("Messages", [])
    assert len(messages) == 0


def test_webhook_future_dated_event_returns_503(
    test_infrastructure: dict[str, Any],
) -> None:
    sqs = test_infrastructure["sqs"]
    queue_url = test_infrastructure["queue_url"]

    # 2 days in future (> 1 day skew tolerance)
    payload = _make_fresh_payload(seconds_ago=-2 * 86400)
    raw_body = json.dumps(payload)
    sig = compute_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    ).hex()
    event = _build_furl_event(body=raw_body, method="POST", signature_header=sig)

    response = lambda_handler(event, None)
    # Must return 503 so Zalo retries after clock skew resolves
    assert response["statusCode"] == 503

    messages = sqs.receive_message(QueueUrl=queue_url).get("Messages", [])
    assert len(messages) == 0


def test_webhook_fail_fast_on_low_remaining_time(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_fresh_payload()
    raw_body = json.dumps(payload)
    sig = compute_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    ).hex()
    event = _build_furl_event(body=raw_body, method="POST", signature_header=sig)

    mock_context = MagicMock()
    # 400ms remaining <= 500ms safety buffer
    mock_context.get_remaining_time_in_millis.return_value = 400

    response = lambda_handler(event, mock_context)
    assert response["statusCode"] == 503
    assert "Timeout" in json.loads(response["body"])["error"]


@pytest.mark.parametrize(
    "invalid_body",
    [
        "",
        "not a json",
        "[]",
    ],
)
def test_webhook_invalid_json(
    test_infrastructure: dict[str, Any], invalid_body: str
) -> None:
    event = _build_furl_event(body=invalid_body, method="POST")
    response = lambda_handler(event, None)
    assert response["statusCode"] == 400


def test_webhook_missing_required_fields(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = {"app_id": TEST_APP_ID, "event_name": "user_send_text"}
    raw_body = json.dumps(payload)
    event = _build_furl_event(body=raw_body, method="POST")
    response = lambda_handler(event, None)
    assert response["statusCode"] == 400
    assert "Validation failed" in json.loads(response["body"])["error"]


def test_webhook_invalid_signature(test_infrastructure: dict[str, Any]) -> None:
    sqs = test_infrastructure["sqs"]
    queue_url = test_infrastructure["queue_url"]

    payload = _make_fresh_payload()
    raw_body = json.dumps(payload)
    fake_sig = "b" * 64
    event = _build_furl_event(
        body=raw_body,
        method="POST",
        signature_header=f"mac={fake_sig}",
    )

    response = lambda_handler(event, None)
    assert response["statusCode"] == 401
    assert "Invalid signature" in json.loads(response["body"])["error"]

    messages = sqs.receive_message(QueueUrl=queue_url).get("Messages", [])
    assert len(messages) == 0


def test_webhook_missing_signature_header(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_fresh_payload()
    raw_body = json.dumps(payload)
    event = _build_furl_event(body=raw_body, method="POST", signature_header=None)

    response = lambda_handler(event, None)
    assert response["statusCode"] == 400
    assert "Validation failed" in json.loads(response["body"])["error"]


def test_secret_caching_across_invocations(
    test_infrastructure: dict[str, Any],
) -> None:
    ssm = test_infrastructure["ssm"]

    secret_1 = get_oa_secret_key(ssm_client=ssm)
    assert secret_1 == TEST_SECRET_KEY

    ssm.delete_parameter(Name=TEST_PARAM_NAME)

    secret_2 = get_oa_secret_key(ssm_client=ssm)
    assert secret_2 == TEST_SECRET_KEY


def test_webhook_queue_error_returns_503(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_fresh_payload()
    raw_body = json.dumps(payload)
    sig = compute_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    ).hex()
    event = _build_furl_event(body=raw_body, method="POST", signature_header=sig)

    with patch("receive_zalo_event.app.get_sqs_client") as mock_sqs:
        mock_sqs.return_value.send_message.side_effect = RuntimeError(
            "SQS connection failed"
        )
        response = lambda_handler(event, None)
        assert response["statusCode"] == 503
        assert "Enqueue failed" in json.loads(response["body"])["error"]
