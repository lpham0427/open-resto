"""Unit tests for Zalo webhook signature verification."""

from api.signature import compute_signature, verify_signature


def test_compute_signature_length() -> None:
    app_id = "123456789"
    raw_body = '{"event_name":"user_send_text"}'
    timestamp = "154390853474"
    secret_key = "my_secret_key"  # noqa: S105

    digest = compute_signature(app_id, raw_body, timestamp, secret_key)
    assert isinstance(digest, bytes)
    assert len(digest) == 32


def test_verify_signature_matching() -> None:
    app_id = "123456789"
    raw_body = '{"event_name":"user_send_text"}'
    timestamp = "154390853474"
    secret_key = "my_secret_key"  # noqa: S105

    valid_sig = compute_signature(app_id, raw_body, timestamp, secret_key)

    assert (
        verify_signature(
            claimed_app_id=app_id,
            trusted_app_id=app_id,
            raw_body=raw_body,
            timestamp=timestamp,
            secret_key=secret_key,
            signature=valid_sig,
        )
        is True
    )


def test_verify_signature_rejects_untrusted_app_id() -> None:
    trusted_app_id = "123456789"
    claimed_app_id = "987654321"  # Attacker tries to claim a different app_id
    raw_body = '{"event_name":"user_send_text"}'
    timestamp = "154390853474"
    secret_key = "my_secret_key"  # noqa: S105

    sig = compute_signature(trusted_app_id, raw_body, timestamp, secret_key)

    assert (
        verify_signature(
            claimed_app_id=claimed_app_id,
            trusted_app_id=trusted_app_id,
            raw_body=raw_body,
            timestamp=timestamp,
            secret_key=secret_key,
            signature=sig,
        )
        is False
    )


def test_verify_signature_rejects_tampered_inputs() -> None:
    app_id = "123456789"
    raw_body = '{"event_name":"user_send_text"}'
    timestamp = "154390853474"
    secret_key = "my_secret_key"  # noqa: S105

    valid_sig = compute_signature(app_id, raw_body, timestamp, secret_key)

    # Tampered body
    assert (
        verify_signature(
            claimed_app_id=app_id,
            trusted_app_id=app_id,
            raw_body='{"tampered":true}',
            timestamp=timestamp,
            secret_key=secret_key,
            signature=valid_sig,
        )
        is False
    )

    # Tampered timestamp
    assert (
        verify_signature(
            claimed_app_id=app_id,
            trusted_app_id=app_id,
            raw_body=raw_body,
            timestamp="999999999999",
            secret_key=secret_key,
            signature=valid_sig,
        )
        is False
    )

    # Wrong secret
    assert (
        verify_signature(
            claimed_app_id=app_id,
            trusted_app_id=app_id,
            raw_body=raw_body,
            timestamp=timestamp,
            secret_key="wrong_secret",  # noqa: S106
            signature=valid_sig,
        )
        is False
    )
