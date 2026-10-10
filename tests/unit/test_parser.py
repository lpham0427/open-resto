"""Unit tests for strict Zalo webhook parser."""

import json
from datetime import UTC, datetime

from receive_zalo_event.parser import (
    SIGNATURE_HEADER,
    extract_signature,
    parse_candidate,
    parse_timestamp,
)

SAMPLE_APP_ID = "360846524940903967"
SAMPLE_TS = "1728000000000"
SAMPLE_SIG_HEX = "a" * 64


def _build_valid_payload() -> str:
    return json.dumps(
        {
            "app_id": SAMPLE_APP_ID,
            "timestamp": SAMPLE_TS,
            "event_name": "user_send_text",
            "sender": {"id": "246845883529197922"},
            "user_id_by_app": "552177279717587730",
            "message": {"text": "hello", "msg_id": "96d3cdf3af150460909"},
        }
    )


def test_parse_candidate_success() -> None:
    raw_body = _build_valid_payload()
    headers = {SIGNATURE_HEADER: f"mac={SAMPLE_SIG_HEX}"}

    candidate, errors = parse_candidate(headers, raw_body)

    assert errors == {}
    assert candidate is not None
    assert candidate.app_id == SAMPLE_APP_ID
    assert candidate.timestamp == SAMPLE_TS
    assert candidate.signature == bytes.fromhex(SAMPLE_SIG_HEX)
    assert candidate.occurred_at == datetime(2024, 10, 4, 0, 0, 0, tzinfo=UTC)
    assert candidate.event_name == "user_send_text"
    assert candidate.user_id == "246845883529197922"
    assert candidate.msg_id == "96d3cdf3af150460909"


def test_parse_candidate_without_mac_prefix() -> None:
    raw_body = _build_valid_payload()
    headers = {SIGNATURE_HEADER: SAMPLE_SIG_HEX}

    candidate, errors = parse_candidate(headers, raw_body)
    assert errors == {}
    assert candidate is not None
    assert candidate.signature == bytes.fromhex(SAMPLE_SIG_HEX)


def test_reject_duplicate_json_keys() -> None:
    raw_body = '{"app_id":"1","app_id":"2","timestamp":"1728000000000"}'
    headers = {SIGNATURE_HEADER: SAMPLE_SIG_HEX}

    candidate, errors = parse_candidate(headers, raw_body)
    assert candidate is None
    assert "duplicate" in errors["Payload"][0]


def test_reject_non_object_json() -> None:
    headers = {SIGNATURE_HEADER: SAMPLE_SIG_HEX}

    for non_object in ('["item"]', '"string"', "12345", "true", "null"):
        candidate, errors = parse_candidate(headers, non_object)
        assert candidate is None
        assert "Payload" in errors


def test_reject_unbounded_or_empty_app_id() -> None:
    headers = {SIGNATURE_HEADER: SAMPLE_SIG_HEX}

    # Empty string
    candidate, errors = parse_candidate(
        headers, json.dumps({"app_id": "", "timestamp": SAMPLE_TS})
    )
    assert candidate is None
    assert "Payload.app_id" in errors

    # String exceeding 256 characters
    candidate, errors = parse_candidate(
        headers, json.dumps({"app_id": "a" * 257, "timestamp": SAMPLE_TS})
    )
    assert candidate is None
    assert "Payload.app_id" in errors


def test_timestamp_parsing() -> None:
    # Valid timestamp in milliseconds
    dt = parse_timestamp("1728000000000")
    assert dt is not None
    assert dt == datetime(2024, 10, 4, 0, 0, 0, tzinfo=UTC)

    # Negative, non-numeric, or non-ASCII
    assert parse_timestamp("-1000") is None
    assert parse_timestamp("123abc") is None
    assert parse_timestamp("") is None
    assert parse_timestamp("12.34") is None
    assert parse_timestamp("0") is None


def test_signature_extraction_edge_cases() -> None:
    # Missing header
    assert extract_signature({}) is None

    # Invalid hex characters (e.g. 'g')
    assert extract_signature({SIGNATURE_HEADER: "g" * 64}) is None

    # Wrong length
    assert extract_signature({SIGNATURE_HEADER: "a" * 63}) is None
    assert extract_signature({SIGNATURE_HEADER: "a" * 65}) is None

    # Comma-joined duplicate header (mac=a...,mac=b...)
    comma_joined = f"mac={SAMPLE_SIG_HEX},mac={SAMPLE_SIG_HEX}"
    assert extract_signature({SIGNATURE_HEADER: comma_joined}) is None


def test_parse_user_id_and_msg_id() -> None:
    raw_body = json.dumps(
        {
            "app_id": SAMPLE_APP_ID,
            "timestamp": SAMPLE_TS,
            "event_name": "user_send_text",
            "sender": {"id": "246845883529197922"},
            "user_id_by_app": "552177279717587730",
            "message": {
                "text": "Cho minh dat 2 suat com",
                "msg_id": "96d3cdf3af150460909",
            },
        }
    )
    headers = {SIGNATURE_HEADER: SAMPLE_SIG_HEX}
    candidate, errors = parse_candidate(headers, raw_body)

    assert errors == {}
    assert candidate is not None
    assert candidate.user_id == "246845883529197922"
    assert candidate.msg_id == "96d3cdf3af150460909"


def test_reject_missing_user_id() -> None:
    raw_body = json.dumps(
        {
            "app_id": SAMPLE_APP_ID,
            "timestamp": SAMPLE_TS,
            "event_name": "user_send_text",
            "message": {"text": "hello"},
        }
    )
    headers = {SIGNATURE_HEADER: SAMPLE_SIG_HEX}
    candidate, errors = parse_candidate(headers, raw_body)
    assert candidate is None
    assert "Payload.user_id" in errors
