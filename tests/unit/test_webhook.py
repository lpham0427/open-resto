"""Unit and integration tests for Zalo webhook Lambda handler."""

import base64
import json
import os
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from api.app import lambda_handler
from api.signature import calculate_signature
from shared.settings import (
    clear_secret_cache,
    get_oa_secret_key,
    get_sqs_client,
    get_ssm_client,
)

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
        queue_res = sqs.create_queue(QueueName="test-zalo-events-queue")
        queue_url = queue_res["QueueUrl"]
        os.environ["EVENTS_QUEUE_URL"] = queue_url

        yield {"ssm": ssm, "sqs": sqs, "queue_url": queue_url}


def _make_sample_payload() -> dict[str, Any]:
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
        "timestamp": "154390853474",
    }


def _build_furl_event(
    body: str,
    method: str = "POST",
    signature_header: str | None = None,
    is_base64: bool = False,
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
            "http": {
                "method": method,
                "path": "/",
                "protocol": "HTTP/1.1",
            }
        },
        "body": body,
        "isBase64Encoded": is_base64,
    }


def test_webhook_success_enqueues_message(
    test_infrastructure: dict[str, Any],
) -> None:
    sqs = test_infrastructure["sqs"]
    queue_url = test_infrastructure["queue_url"]

    payload = _make_sample_payload()
    raw_body = json.dumps(payload, separators=(",", ":"))
    sig = calculate_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    )

    event = _build_furl_event(
        body=raw_body,
        method="POST",
        signature_header=f"mac = {sig}",
    )

    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    body_data = json.loads(response["body"])
    assert body_data["status"] == "ok"

    # Verify message in SQS
    messages = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        MessageAttributeNames=["All"],
    ).get("Messages", [])

    assert len(messages) == 1
    received = messages[0]
    assert received["Body"] == raw_body
    attrs = received["MessageAttributes"]
    assert attrs["event_name"]["StringValue"] == "user_send_text"
    assert attrs["app_id"]["StringValue"] == TEST_APP_ID


def test_webhook_base64_encoded_body(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_sample_payload()
    raw_body = json.dumps(payload, separators=(",", ":"))
    sig = calculate_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    )
    b64_body = base64.b64encode(raw_body.encode("utf-8")).decode("utf-8")

    event = _build_furl_event(
        body=b64_body,
        method="POST",
        signature_header=sig,
        is_base64=True,
    )

    response = lambda_handler(event, None)
    assert response["statusCode"] == 200


def test_webhook_method_not_allowed(
    test_infrastructure: dict[str, Any],
) -> None:
    event = _build_furl_event(body="{}", method="GET")
    response = lambda_handler(event, None)
    assert response["statusCode"] == 405
    assert json.loads(response["body"])["error"] == "Method Not Allowed"


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
    # Missing timestamp
    payload = {"app_id": TEST_APP_ID, "event_name": "user_send_text"}
    raw_body = json.dumps(payload)
    event = _build_furl_event(body=raw_body, method="POST")
    response = lambda_handler(event, None)
    assert response["statusCode"] == 400
    assert "Missing" in json.loads(response["body"])["error"]


def test_webhook_invalid_signature(test_infrastructure: dict[str, Any]) -> None:
    sqs = test_infrastructure["sqs"]
    queue_url = test_infrastructure["queue_url"]

    payload = _make_sample_payload()
    raw_body = json.dumps(payload)
    event = _build_furl_event(
        body=raw_body,
        method="POST",
        signature_header="mac=invalid_signature_hex",
    )

    response = lambda_handler(event, None)
    assert response["statusCode"] == 401
    assert "Invalid signature" in json.loads(response["body"])["error"]

    # Queue must remain empty
    messages = sqs.receive_message(QueueUrl=queue_url).get("Messages", [])
    assert len(messages) == 0


def test_webhook_missing_signature_header(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_sample_payload()
    raw_body = json.dumps(payload)
    event = _build_furl_event(body=raw_body, method="POST", signature_header=None)

    response = lambda_handler(event, None)
    assert response["statusCode"] == 401


def test_secret_caching_across_invocations(
    test_infrastructure: dict[str, Any],
) -> None:
    ssm = test_infrastructure["ssm"]

    # First fetch: populates cache
    secret_1 = get_oa_secret_key(ssm_client=ssm)
    assert secret_1 == TEST_SECRET_KEY

    # Delete parameter in SSM backend
    ssm.delete_parameter(Name=TEST_PARAM_NAME)

    # Second fetch: served from cache without exception
    secret_2 = get_oa_secret_key(ssm_client=ssm)
    assert secret_2 == TEST_SECRET_KEY


def test_webhook_queue_error_returns_500(
    test_infrastructure: dict[str, Any],
) -> None:
    payload = _make_sample_payload()
    raw_body = json.dumps(payload)
    sig = calculate_signature(
        TEST_APP_ID, raw_body, payload["timestamp"], TEST_SECRET_KEY
    )
    event = _build_furl_event(body=raw_body, method="POST", signature_header=sig)

    # Simulate SQS client failure
    with patch("api.app.get_sqs_client") as mock_sqs:
        mock_sqs.return_value.send_message.side_effect = RuntimeError("SQS unavailable")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 500
        assert "Failed to enqueue" in json.loads(response["body"])["error"]
