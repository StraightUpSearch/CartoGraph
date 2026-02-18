"""
Unit tests for alert business logic (no database required).

Covers:
  - Valid/invalid alert type validation
  - TierGate alert limit enforcement across tiers
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.alerts import _VALID_ALERT_TYPES
from app.tier_gating import TierGate


# ---------------------------------------------------------------------------
# Alert type constants
# ---------------------------------------------------------------------------


def test_valid_alert_types_defined() -> None:
    assert "new_domain" in _VALID_ALERT_TYPES
    assert "tech_change" in _VALID_ALERT_TYPES
    assert "dr_change" in _VALID_ALERT_TYPES
    assert "serp_feature" in _VALID_ALERT_TYPES


def test_invalid_alert_type_not_in_set() -> None:
    assert "foo_alert" not in _VALID_ALERT_TYPES
    assert "domain.created" not in _VALID_ALERT_TYPES  # that's a webhook event type


# ---------------------------------------------------------------------------
# Alert limits per tier
# ---------------------------------------------------------------------------


def test_free_tier_zero_alerts() -> None:
    gate = TierGate("free")
    assert gate.limits.max_alerts == 0
    with pytest.raises(HTTPException) as exc_info:
        gate.check_alert_limit(0)
    assert exc_info.value.status_code == 403


def test_starter_tier_allows_five_alerts() -> None:
    gate = TierGate("starter")
    assert gate.limits.max_alerts == 5
    # 0–4 should all be fine
    for count in range(5):
        gate.check_alert_limit(count)


def test_starter_tier_blocks_sixth_alert() -> None:
    gate = TierGate("starter")
    with pytest.raises(HTTPException) as exc_info:
        gate.check_alert_limit(5)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["limit"] == 5


def test_professional_tier_allows_50_alerts() -> None:
    gate = TierGate("professional")
    assert gate.limits.max_alerts == 50
    gate.check_alert_limit(49)  # should not raise


def test_professional_tier_blocks_51st_alert() -> None:
    gate = TierGate("professional")
    with pytest.raises(HTTPException):
        gate.check_alert_limit(50)


def test_business_tier_unlimited_alerts() -> None:
    gate = TierGate("business")
    assert gate.limits.max_alerts is None
    gate.check_alert_limit(99_999)  # should not raise


def test_enterprise_tier_unlimited_alerts() -> None:
    gate = TierGate("enterprise")
    assert gate.limits.max_alerts is None
    gate.check_alert_limit(1_000_000)  # should not raise


# ---------------------------------------------------------------------------
# Error detail structure
# ---------------------------------------------------------------------------


def test_alert_limit_error_has_expected_keys() -> None:
    gate = TierGate("starter")
    with pytest.raises(HTTPException) as exc_info:
        gate.check_alert_limit(5)
    detail = exc_info.value.detail
    assert "code" in detail
    assert "limit" in detail
    assert "current_tier" in detail
    assert detail["code"] == "alert_limit_reached"
    assert detail["current_tier"] == "starter"
