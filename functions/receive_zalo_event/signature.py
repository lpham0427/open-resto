"""Zalo OA webhook signature verification."""

import hashlib
import hmac


def compute_signature(
    app_id: str, raw_body: str, timestamp: str, secret_key: str
) -> bytes:
    """Compute the expected SHA-256 digest.

    Formula: sha256(appId + data + timeStamp + OAsecretKey), where `data` is the
    raw request body exactly as received.
    """
    content = f"{app_id}{raw_body}{timestamp}{secret_key}"
    return hashlib.sha256(content.encode("utf-8")).digest()


def verify_signature(
    *,
    claimed_app_id: str,
    trusted_app_id: str,
    raw_body: str,
    timestamp: str,
    secret_key: str,
    signature: bytes,
) -> bool:
    """Verify a webhook signature in constant time.

    The app_id claimed by the payload is untrusted input: it must equal the
    configured app_id, and the digest is always computed from the *trusted*
    value, never from the claimed one.
    """
    if not hmac.compare_digest(
        claimed_app_id.encode("utf-8"), trusted_app_id.encode("utf-8")
    ):
        return False
    expected = compute_signature(trusted_app_id, raw_body, timestamp, secret_key)
    return hmac.compare_digest(expected, signature)
