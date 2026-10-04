"""Unit tests for Zalo webhook signature verification."""

import pytest

from api.signature import calculate_signature, extract_signature, verify_signature


def test_extract_signature_formats() -> None:
    assert extract_signature(None) is None
    assert extract_signature("") is None
    assert extract_signature("   ") is None
    assert extract_signature("abc123def") == "abc123def"
    assert extract_signature("mac=abc123def") == "abc123def"
    assert extract_signature("mac = abc123def") == "abc123def"
    assert extract_signature("MAC=ABC123DEF") == "ABC123DEF"
    assert extract_signature("  mac =  abc123def  ") == "abc123def"


def test_calculate_and_verify_signature_valid() -> None:
    app_id = "123456789"
    raw_body = '{"event_name":"user_send_text","message":{"text":"hello"}}'
    timestamp = "154390853474"
    secret_key = "my_super_secret_oa_key"  # noqa: S105

    expected_sig = calculate_signature(app_id, raw_body, timestamp, secret_key)
    assert len(expected_sig) == 64

    # Direct match
    assert (
        verify_signature(app_id, raw_body, timestamp, secret_key, expected_sig) is True
    )

    # With 'mac = ' prefix
    header_with_prefix = f"mac = {expected_sig}"
    assert (
        verify_signature(app_id, raw_body, timestamp, secret_key, header_with_prefix)
        is True
    )


@pytest.mark.parametrize(
    ("bad_sig", "bad_secret", "bad_ts", "bad_body"),
    [
        (
            "wrong_signature_value",
            "my_super_secret_oa_key",
            "154390853474",
            "{}",
        ),
        (None, "my_super_secret_oa_key", "154390853474", "{}"),
        ("", "my_super_secret_oa_key", "154390853474", "{}"),
    ],
)
def test_verify_signature_invalid(
    bad_sig: str | None, bad_secret: str, bad_ts: str, bad_body: str
) -> None:
    assert (
        verify_signature(
            app_id="123",
            raw_body=bad_body,
            timestamp=bad_ts,
            secret_key=bad_secret,
            signature_header=bad_sig,
        )
        is False
    )


def test_verify_signature_mismatched_inputs() -> None:
    app_id = "123456789"
    raw_body = '{"event_name":"user_send_text"}'
    timestamp = "154390853474"
    secret_key = "secret_one"  # noqa: S105

    sig = calculate_signature(app_id, raw_body, timestamp, secret_key)

    # Wrong secret
    assert (
        verify_signature(app_id, raw_body, timestamp, "different_secret", sig) is False
    )

    # Tampered body
    assert (
        verify_signature(app_id, '{"tampered":true}', timestamp, secret_key, sig)
        is False
    )

    # Tampered timestamp
    assert verify_signature(app_id, raw_body, "999999999999", secret_key, sig) is False
