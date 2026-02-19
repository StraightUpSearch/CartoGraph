"""
Unit tests for stripe_billing.py

Tests are deliberately thin on Stripe SDK internals (we don't want to test
Stripe's library) but comprehensively cover our own logic:
  - PLAN_CATALOGUE structure and completeness
  - Price-to-tier mapping helper
  - Founding member counter helpers (using a mock DB session)
  - Webhook event dispatcher routing
  - Each webhook event handler (mock workspace, mock session)
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.stripe_billing import (
    PLAN_CATALOGUE,
    _handle_checkout_completed,
    _handle_invoice_paid,
    _handle_invoice_payment_failed,
    _handle_subscription_deleted,
    _handle_subscription_updated,
    get_founding_member_count,
    increment_founding_member_count,
    process_webhook_event,
)


# ---------------------------------------------------------------------------
# PLAN_CATALOGUE
# ---------------------------------------------------------------------------

EXPECTED_TIERS = {"free", "starter", "professional", "business", "enterprise"}


def test_plan_catalogue_has_all_tiers():
    tiers = {p["tier"] for p in PLAN_CATALOGUE}
    assert tiers == EXPECTED_TIERS


def test_plan_catalogue_required_keys():
    required = {"tier", "name", "price_monthly_gbp", "description", "limits", "highlights"}
    for plan in PLAN_CATALOGUE:
        assert required.issubset(plan.keys()), f"Missing keys in {plan['tier']}"


def test_free_plan_has_zero_prices():
    free = next(p for p in PLAN_CATALOGUE if p["tier"] == "free")
    assert free["price_monthly_gbp"] == 0
    assert free["price_annual_gbp"] == 0


def test_professional_has_founding_member():
    pro = next(p for p in PLAN_CATALOGUE if p["tier"] == "professional")
    assert "founding_member" in pro
    fm = pro["founding_member"]
    assert fm["price_annual_gbp"] == 60  # 50% off £119/mo annual (£99/mo)
    assert "cap" in fm


def test_enterprise_has_no_annual_price():
    ent = next(p for p in PLAN_CATALOGUE if p["tier"] == "enterprise")
    assert ent["price_annual_gbp"] is None


def test_limits_structure():
    limit_keys = {"domain_lookups", "rows_per_view", "csv_credits", "api_calls", "alerts"}
    for plan in PLAN_CATALOGUE:
        assert limit_keys == set(plan["limits"].keys()), (
            f"Unexpected limit keys in {plan['tier']}"
        )


# ---------------------------------------------------------------------------
# Price-to-tier map
# ---------------------------------------------------------------------------

def test_price_to_tier_map_skips_empty_price_ids():
    """With no env vars set, no price_ids are populated → map is empty."""
    from app.stripe_billing import get_stripe_price_to_tier_map as _map_fn
    from app.config.variables import cg_settings

    # All price IDs default to "" — map should be empty
    original_starter = cg_settings.STRIPE_PRICE_STARTER_MONTHLY
    # Ensure it's empty (default)
    cg_settings.STRIPE_PRICE_STARTER_MONTHLY = ""
    result = _map_fn()
    cg_settings.STRIPE_PRICE_STARTER_MONTHLY = original_starter

    # result is a dict; empty price IDs must not appear as keys
    for key in result:
        assert key != ""


def test_price_to_tier_map_with_env_prices():
    """If a price ID is set it should map to the correct tier."""
    from app.config.variables import cg_settings
    from app.stripe_billing import get_stripe_price_to_tier_map as _map_fn

    original = cg_settings.STRIPE_PRICE_STARTER_MONTHLY
    cg_settings.STRIPE_PRICE_STARTER_MONTHLY = "price_test_starter_monthly"
    try:
        tier_map = _map_fn()
        assert tier_map.get("price_test_starter_monthly") == "starter"
    finally:
        cg_settings.STRIPE_PRICE_STARTER_MONTHLY = original


# ---------------------------------------------------------------------------
# Founding member counter helpers (mock DB session)
# ---------------------------------------------------------------------------

def _mock_session_with_count(count: int) -> MagicMock:
    session = MagicMock()
    session.exec.return_value.first.return_value = (count,)
    return session


def test_get_founding_member_count_returns_int():
    session = _mock_session_with_count(42)
    result = get_founding_member_count(session)
    assert result == 42


def test_get_founding_member_count_no_row():
    session = MagicMock()
    session.exec.return_value.first.return_value = None
    result = get_founding_member_count(session)
    assert result == 0


def test_increment_founding_member_count():
    session = MagicMock()
    # After UPDATE, SELECT returns 1
    session.exec.return_value.first.return_value = (1,)
    result = increment_founding_member_count(session)
    assert result == 1
    session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Webhook event dispatcher
# ---------------------------------------------------------------------------

def _make_event(event_type: str, data: dict) -> dict:
    return {"type": event_type, "data": {"object": data}}


def test_process_webhook_unknown_event_ignored():
    event = _make_event("customer.created", {})
    result = process_webhook_event(event, MagicMock())
    assert result["action"] == "ignored"
    assert result["event_type"] == "customer.created"


# ---------------------------------------------------------------------------
# _handle_checkout_completed
# ---------------------------------------------------------------------------

def _make_workspace(**kwargs) -> MagicMock:
    ws = MagicMock()
    for k, v in kwargs.items():
        setattr(ws, k, v)
    return ws


def test_checkout_completed_no_workspace_id():
    data = {"client_reference_id": None, "metadata": {}}
    result = _handle_checkout_completed(data, MagicMock(), MagicMock(), MagicMock())
    assert result["action"] == "skipped"
    assert "workspace_id" in result["reason"]


def test_checkout_completed_workspace_not_found():
    session = MagicMock()
    session.get.return_value = None
    data = {"client_reference_id": "00000000-0000-0000-0000-000000000001"}
    result = _handle_checkout_completed(data, session, MagicMock(), MagicMock())
    assert result["action"] == "skipped"
    assert result["reason"] == "workspace_not_found"


def test_checkout_completed_happy_path_no_founding():
    """Non-founding checkout sets customer/subscription IDs and resolves tier."""
    import uuid

    ws = _make_workspace(
        stripe_customer_id=None,
        stripe_subscription_id=None,
        stripe_subscription_status=None,
        founding_member=False,
        stripe_price_id=None,
        tier="free",
    )
    session = MagicMock()
    session.get.return_value = ws

    ws_id = str(uuid.uuid4())
    data = {
        "client_reference_id": ws_id,
        "subscription": "sub_abc",
        "customer": "cus_abc",
        "metadata": {"founding_member": "false"},
    }

    mock_sub = {"items": {"data": [{"price": {"id": "price_starter_monthly"}}]}}

    with (
        patch("app.stripe_billing._stripe_client") as mock_client_fn,
        patch("app.stripe_billing.get_stripe_price_to_tier_map") as mock_map,
    ):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.subscriptions.retrieve.return_value = mock_sub
        mock_map.return_value = {"price_starter_monthly": "starter"}

        result = _handle_checkout_completed(data, session, MagicMock(), MagicMock())

    assert result["action"] == "checkout_activated"
    assert ws.stripe_customer_id == "cus_abc"
    assert ws.stripe_subscription_id == "sub_abc"
    assert ws.stripe_subscription_status == "active"
    assert ws.tier == "starter"


def test_checkout_completed_founding_increments_count():
    import uuid
    from app.config.variables import cg_settings

    ws = _make_workspace(
        stripe_customer_id=None,
        stripe_subscription_id=None,
        stripe_subscription_status=None,
        founding_member=False,
        stripe_price_id=None,
        tier="free",
    )
    session = MagicMock()
    session.get.return_value = ws

    ws_id = str(uuid.uuid4())
    data = {
        "client_reference_id": ws_id,
        "subscription": "sub_founding",
        "customer": "cus_founding",
        "metadata": {"founding_member": "true"},
    }

    mock_sub = {"items": {"data": [{"price": {"id": "price_pro_founding"}}]}}

    with (
        patch("app.stripe_billing._stripe_client") as mock_client_fn,
        patch("app.stripe_billing.get_stripe_price_to_tier_map") as mock_map,
        patch("app.stripe_billing.get_founding_member_count") as mock_count,
        patch("app.stripe_billing.increment_founding_member_count") as mock_inc,
    ):
        mock_client_fn.return_value.subscriptions.retrieve.return_value = mock_sub
        mock_map.return_value = {"price_pro_founding": "professional"}
        mock_count.return_value = 5  # below cap

        result = _handle_checkout_completed(data, session, MagicMock(), MagicMock())

    assert result["action"] == "checkout_activated"
    assert ws.founding_member is True
    mock_inc.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_subscription_updated
# ---------------------------------------------------------------------------

def test_subscription_updated_workspace_not_found():
    session = MagicMock()
    session.exec.return_value.first.return_value = None
    data = {"id": "sub_xyz", "items": {"data": [{"price": {"id": "p1"}}]}, "status": "active"}
    result = _handle_subscription_updated(data, session, MagicMock(), MagicMock())
    assert result["action"] == "skipped"


def test_subscription_updated_changes_tier():
    ws = _make_workspace(tier="starter", stripe_price_id="old", stripe_subscription_status="active")
    session = MagicMock()
    session.exec.return_value.first.return_value = ws

    data = {
        "id": "sub_xyz",
        "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        "status": "active",
    }

    with patch("app.stripe_billing.get_stripe_price_to_tier_map") as mock_map:
        mock_map.return_value = {"price_pro_monthly": "professional"}
        result = _handle_subscription_updated(data, session, MagicMock(), MagicMock())

    assert result["action"] == "tier_updated"
    assert ws.tier == "professional"


# ---------------------------------------------------------------------------
# _handle_subscription_deleted
# ---------------------------------------------------------------------------

def test_subscription_deleted_downgrades_to_free():
    ws = _make_workspace(
        tier="professional",
        stripe_subscription_id="sub_del",
        stripe_subscription_status="active",
        stripe_price_id="price_pro",
    )
    session = MagicMock()
    session.exec.return_value.first.return_value = ws

    data = {"id": "sub_del"}
    result = _handle_subscription_deleted(data, session, MagicMock(), MagicMock())

    assert result["action"] == "downgraded_to_free"
    assert ws.tier == "free"
    assert ws.stripe_subscription_id is None
    assert ws.stripe_price_id is None
    assert ws.stripe_subscription_status == "cancelled"


# ---------------------------------------------------------------------------
# _handle_invoice_paid
# ---------------------------------------------------------------------------

def test_invoice_paid_resets_usage():
    ws = _make_workspace(
        domain_lookups_used=400,
        export_credits_used=45,
        api_calls_used=9000,
        billing_cycle_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session = MagicMock()
    session.exec.return_value.first.return_value = ws

    data = {"customer": "cus_abc"}
    result = _handle_invoice_paid(data, session, MagicMock(), MagicMock())

    assert result["action"] == "usage_reset"
    assert ws.domain_lookups_used == 0
    assert ws.export_credits_used == 0
    assert ws.api_calls_used == 0
    # billing_cycle_start should be updated to "now"
    assert ws.billing_cycle_start.year == datetime.now(timezone.utc).year


# ---------------------------------------------------------------------------
# _handle_invoice_payment_failed
# ---------------------------------------------------------------------------

def test_invoice_payment_failed_sets_past_due():
    ws = _make_workspace(stripe_subscription_status="active")
    session = MagicMock()
    session.exec.return_value.first.return_value = ws

    data = {"customer": "cus_abc"}
    result = _handle_invoice_payment_failed(data, session, MagicMock(), MagicMock())

    assert result["action"] == "marked_past_due"
    assert ws.stripe_subscription_status == "past_due"


def test_invoice_payment_failed_workspace_not_found():
    session = MagicMock()
    session.exec.return_value.first.return_value = None
    data = {"customer": "cus_missing"}
    result = _handle_invoice_payment_failed(data, session, MagicMock(), MagicMock())
    assert result["action"] == "skipped"
