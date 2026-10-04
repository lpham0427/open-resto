"""Zalo OA webhook signature verification."""

import hashlib
import hmac
import re


def extract_signature(signature_header: str | None) -> str | None:
    """Extract hex signature from X-ZEvent-Signature header.

    The header can be formatted as 'mac=<hex>', 'mac = <hex>', or raw '<hex>'.
    """
    if not signature_header:
        return None
    cleaned = signature_header.strip()
    if not cleaned:
        return None
    stripped = re.sub(r"^mac\s*=\s*", "", cleaned, flags=re.IGNORECASE)
    return stripped.strip() or None


def calculate_signature(
    app_id: str, raw_body: str, timestamp: str, secret_key: str
) -> str:
    """Calculate expected SHA256 signature for Zalo webhook event.

    Formula: sha256(appId + data + timeStamp + OAsecretKey)
    """
    content = f"{app_id}{raw_body}{timestamp}{secret_key}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_signature(
    app_id: str,
    raw_body: str,
    timestamp: str,
    secret_key: str,
    signature_header: str | None,
) -> bool:
    """Verify that incoming request signature matches expected signature.

    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    received = extract_signature(signature_header)
    if not received:
        return False
    expected = calculate_signature(app_id, raw_body, timestamp, secret_key)
    return hmac.compare_digest(expected.lower(), received.lower())
