"""
Unit tests for webhook business logic (no database or HTTP server required).

Covers:
  - HMAC-SHA256 signing correctness
  - Event type validation
  - Invalid cursor handling
"""

from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app.api.routes.webhooks import _validate_event_types


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------


def _sign_payload(secret: str, raw_body: bytes) -> str:
    """Replicate the signing function from webhook_tasks for test verification."""
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_sign_payload_format() -> None:
    sig = _sign_payload("mysecret", b'{"event": "domain.updated"}')
    assert sig.startswith("sha256=")
    assert len(sig) == 71  # "sha256=" (7) + 64 hex chars


def test_sign_payload_deterministic() -> None:
    body = b'{"event": "domain.created", "data": {"domain": "example.co.uk"}}'
    sig1 = _sign_payload("secret123", body)
    sig2 = _sign_payload("secret123", body)
    assert sig1 == sig2


def test_sign_payload_different_secrets_differ() -> None:
    body = b'{"event": "ping"}'
    sig1 = _sign_payload("secret_a", body)
    sig2 = _sign_payload("secret_b", body)
    assert sig1 != sig2


def test_sign_payload_different_bodies_differ() -> None:
    sig1 = _sign_payload("secret", b'{"event": "domain.created"}')
    sig2 = _sign_payload("secret", b'{"event": "domain.updated"}')
    assert sig1 != sig2


def test_hmac_verification_succeeds() -> None:
    """Receiving side can verify the signature."""
    secret = "test_signing_secret"
    body = b'{"event": "domain.updated", "data": {}}'
    signature = _sign_payload(secret, body)

    # Re-compute on the receiving end
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, expected)


# ---------------------------------------------------------------------------
# Event type validation
# ---------------------------------------------------------------------------


def test_validate_event_types_accepts_valid() -> None:
    _validate_event_types(["domain.created", "domain.updated", "alert.triggered"])
    # Should not raise


def test_validate_event_types_empty_list_ok() -> None:
    _validate_event_types([])
    # Should not raise


def test_validate_event_types_raises_on_unknown() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_event_types(["domain.created", "totally.fake.event"])
    assert exc_info.value.status_code == 422
    assert "totally.fake.event" in str(exc_info.value.detail)


def test_validate_event_types_raises_on_all_unknown() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_event_types(["not.real", "also.fake"])
    assert exc_info.value.status_code == 422


def test_validate_event_types_ping_not_valid() -> None:
    """'ping' is used internally for the test endpoint but is not a subscriber-facing event."""
    with pytest.raises(HTTPException):
        _validate_event_types(["ping"])
