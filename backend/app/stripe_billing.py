"""
CartoGraph Stripe billing module

Handles:
  - Checkout session creation (hosted Stripe checkout)
  - Billing portal session (Stripe Customer Portal for self-service)
  - Webhook event processing (subscription lifecycle + billing cycle reset)
  - Founding Member programme enforcement (200-seat cap, 50% off annual Pro)

Tier mapping is driven by the Stripe price_id → tier lookup table built from
environment variables in config/variables.py.

IMPORTANT: This module is deliberately thin. All business logic (tier limits,
field masking) lives in tier_gating.py. This module's only job is to keep the
Stripe state and workspace state in sync.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import stripe

from app.config.variables import cg_settings, get_stripe_price_to_tier_map

log = logging.getLogger(__name__)

# Initialise Stripe SDK lazily (no key required at import time)
def _stripe_client() -> stripe.StripeClient:
    if not cg_settings.STRIPE_SECRET_KEY:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not set. "
            "Set it in your .env file before using billing features."
        )
    return stripe.StripeClient(api_key=cg_settings.STRIPE_SECRET_KEY)


# ---------------------------------------------------------------------------
# Plan catalogue
# ---------------------------------------------------------------------------

PLAN_CATALOGUE: list[dict[str, Any]] = [
    {
        "tier": "free",
        "name": "Free",
        "price_monthly_gbp": 0,
        "price_annual_gbp": 0,
        "description": "Get started with UK ecommerce intelligence",
        "limits": {
            "domain_lookups": 25,
            "rows_per_view": 100,
            "csv_credits": 0,
            "api_calls": 0,
            "alerts": 0,
        },
        "highlights": [
            "25 domain lookups/month",
            "8 data fields per domain",
            "100 rows per table view",
            "Community support",
        ],
    },
    {
        "tier": "starter",
        "name": "Starter",
        "price_monthly_gbp": 39,
        "price_annual_gbp": 33,  # ~15% off
        "description": "For freelancers and small agencies",
        "stripe_price_monthly": cg_settings.STRIPE_PRICE_STARTER_MONTHLY,
        "stripe_price_annual": cg_settings.STRIPE_PRICE_STARTER_ANNUAL,
        "limits": {
            "domain_lookups": 500,
            "rows_per_view": 5000,
            "csv_credits": 50,
            "api_calls": 0,
            "alerts": 5,
        },
        "highlights": [
            "500 lookups/month",
            "20 data fields per domain",
            "5,000 rows per view",
            "50 CSV export credits",
            "5 saved alerts",
            "Email support",
        ],
    },
    {
        "tier": "professional",
        "name": "Professional",
        "price_monthly_gbp": 119,
        "price_annual_gbp": 99,  # ~17% off
        "description": "For growing ecommerce teams",
        "stripe_price_monthly": cg_settings.STRIPE_PRICE_PRO_MONTHLY,
        "stripe_price_annual": cg_settings.STRIPE_PRICE_PRO_ANNUAL,
        "limits": {
            "domain_lookups": None,  # unlimited
            "rows_per_view": 50000,
            "csv_credits": 500,
            "api_calls": 10000,
            "alerts": 50,
        },
        "highlights": [
            "Unlimited lookups",
            "All data fields",
            "50,000 rows per view",
            "500 CSV export credits",
            "API access (10K calls/mo)",
            "50 saved alerts",
            "Webhooks",
            "Priority support",
        ],
        "founding_member": {
            "price_annual_gbp": 60,  # 50% off annual Pro
            "stripe_price_id": cg_settings.STRIPE_PRICE_PRO_FOUNDING,
            "cap": cg_settings.FOUNDING_MEMBER_CAP,
            "description": "Lock in 50% off annual Professional for life. "
            f"Limited to {cg_settings.FOUNDING_MEMBER_CAP} seats.",
        },
    },
    {
        "tier": "business",
        "name": "Business",
        "price_monthly_gbp": 279,
        "price_annual_gbp": 232,  # ~17% off
        "description": "For agencies and enterprise teams",
        "stripe_price_monthly": cg_settings.STRIPE_PRICE_BUSINESS_MONTHLY,
        "stripe_price_annual": cg_settings.STRIPE_PRICE_BUSINESS_ANNUAL,
        "limits": {
            "domain_lookups": None,
            "rows_per_view": 250000,
            "csv_credits": 2000,
            "api_calls": 50000,
            "alerts": None,
        },
        "highlights": [
            "Unlimited lookups",
            "250,000 rows per view",
            "2,000 CSV export credits",
            "API access (50K calls/mo)",
            "Historical data (12 months)",
            "Unlimited alerts",
            "SSO (coming soon)",
            "SLA support",
        ],
    },
    {
        "tier": "enterprise",
        "name": "Enterprise",
        "price_monthly_gbp": 749,
        "price_annual_gbp": None,  # custom
        "description": "For large teams with custom needs",
        "stripe_price_monthly": cg_settings.STRIPE_PRICE_ENTERPRISE_MONTHLY,
        "limits": {
            "domain_lookups": None,
            "rows_per_view": None,
            "csv_credits": None,
            "api_calls": None,
            "alerts": None,
        },
        "highlights": [
            "Everything in Business",
            "Unlimited everything",
            "Full history",
            "Custom SLA",
            "Dedicated success manager",
            "Custom integrations",
        ],
    },
]


# ---------------------------------------------------------------------------
# Checkout session
# ---------------------------------------------------------------------------


def create_checkout_session(
    *,
    price_id: str,
    stripe_customer_id: str | None,
    workspace_id: str,
    user_email: str,
    is_founding_member_price: bool = False,
) -> str:
    """
    Create a Stripe checkout session and return the hosted URL.

    Args:
        price_id: Stripe price ID to subscribe to.
        stripe_customer_id: Existing customer ID (None for new customers).
        workspace_id: Used as metadata to link subscription back to workspace.
        user_email: Pre-fills the Stripe checkout email field.
        is_founding_member_price: If True, mark workspace as founding member on success.

    Returns:
        The Stripe checkout session URL (redirect the user to this).
    """
    client = _stripe_client()
    success_url = (
        f"{cg_settings.APP_BASE_URL}/workspaces?billing=success"
        "&session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = f"{cg_settings.APP_BASE_URL}/pricing?billing=cancelled"

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": user_email if not stripe_customer_id else None,
        "client_reference_id": workspace_id,
        "metadata": {
            "workspace_id": workspace_id,
            "founding_member": "true" if is_founding_member_price else "false",
        },
        "subscription_data": {
            "metadata": {"workspace_id": workspace_id},
        },
        "allow_promotion_codes": True,
        "billing_address_collection": "required",
    }
    if stripe_customer_id:
        params["customer"] = stripe_customer_id

    session = client.checkout.sessions.create(params=params)
    return str(session.url)


# ---------------------------------------------------------------------------
# Billing portal
# ---------------------------------------------------------------------------


def create_billing_portal_session(
    *,
    stripe_customer_id: str,
    return_url: str | None = None,
) -> str:
    """
    Create a Stripe billing portal session for the customer.
    Returns the portal URL (redirect the user to this).
    """
    client = _stripe_client()
    portal = client.billing_portal.sessions.create(
        params={
            "customer": stripe_customer_id,
            "return_url": return_url or f"{cg_settings.APP_BASE_URL}/workspaces",
        }
    )
    return str(portal.url)


# ---------------------------------------------------------------------------
# Founding member counter
# ---------------------------------------------------------------------------


def get_founding_member_count(session: Any) -> int:
    """Return the current founding member count from the singleton table."""
    result = session.exec(
        __import__("sqlmodel").text("SELECT count FROM founding_member_count WHERE id = 1")
    ).first()
    return int(result[0]) if result else 0


def increment_founding_member_count(session: Any) -> int:
    """Atomically increment and return the new founding member count."""
    session.exec(
        __import__("sqlmodel").text(
            "UPDATE founding_member_count SET count = count + 1 WHERE id = 1"
        )
    )
    session.commit()
    return get_founding_member_count(session)


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    """Verify and construct a Stripe webhook event from raw request body."""
    return stripe.Webhook.construct_event(
        payload, sig_header, cg_settings.STRIPE_WEBHOOK_SECRET
    )


def process_webhook_event(event: stripe.Event, session: Any) -> dict[str, str]:
    """
    Dispatch a Stripe webhook event and update workspace state accordingly.

    Handled events:
      checkout.session.completed   → set stripe_customer_id, tier, subscription IDs
      customer.subscription.updated → update tier + status
      customer.subscription.deleted → downgrade to free
      invoice.paid                 → reset monthly usage counters (new billing cycle)
      invoice.payment_failed       → set status to past_due

    Returns a dict with action taken (for logging).
    """
    from sqlmodel import select

    from app.models import Workspace

    event_type: str = event["type"]
    data = event["data"]["object"]

    log.info("stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(data, session, Workspace, select)
    elif event_type == "customer.subscription.updated":
        return _handle_subscription_updated(data, session, Workspace, select)
    elif event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(data, session, Workspace, select)
    elif event_type == "invoice.paid":
        return _handle_invoice_paid(data, session, Workspace, select)
    elif event_type == "invoice.payment_failed":
        return _handle_invoice_payment_failed(data, session, Workspace, select)
    else:
        return {"action": "ignored", "event_type": event_type}


def _handle_checkout_completed(
    data: dict[str, Any],
    session: Any,
    Workspace: Any,
    select: Any,
) -> dict[str, str]:
    workspace_id = data.get("client_reference_id") or (
        data.get("metadata") or {}
    ).get("workspace_id")
    if not workspace_id:
        return {"action": "skipped", "reason": "no workspace_id in session"}

    import uuid as _uuid
    ws = session.get(Workspace, _uuid.UUID(workspace_id))
    if not ws:
        return {"action": "skipped", "reason": "workspace_not_found"}

    subscription_id = data.get("subscription")
    customer_id = data.get("customer")
    founding = (data.get("metadata") or {}).get("founding_member") == "true"

    ws.stripe_customer_id = customer_id
    ws.stripe_subscription_id = subscription_id
    ws.stripe_subscription_status = "active"

    if founding:
        current = get_founding_member_count(session)
        if current < cg_settings.FOUNDING_MEMBER_CAP:
            ws.founding_member = True
            increment_founding_member_count(session)

    # Resolve tier from subscription price
    if subscription_id:
        client = _stripe_client()
        sub = client.subscriptions.retrieve(subscription_id)
        price_id = sub["items"]["data"][0]["price"]["id"]
        ws.stripe_price_id = price_id
        ws.tier = get_stripe_price_to_tier_map().get(price_id, "free")

    session.add(ws)
    session.commit()
    return {"action": "checkout_activated", "workspace_id": workspace_id}


def _handle_subscription_updated(
    data: dict[str, Any],
    session: Any,
    Workspace: Any,
    select: Any,
) -> dict[str, str]:
    sub_id = data.get("id")
    ws = session.exec(
        select(Workspace).where(Workspace.stripe_subscription_id == sub_id)
    ).first()
    if not ws:
        return {"action": "skipped", "reason": "workspace_not_found"}

    price_id: str = data["items"]["data"][0]["price"]["id"]
    ws.stripe_price_id = price_id
    ws.tier = get_stripe_price_to_tier_map().get(price_id, "free")
    ws.stripe_subscription_status = data.get("status", "active")

    session.add(ws)
    session.commit()
    return {"action": "tier_updated", "tier": ws.tier}


def _handle_subscription_deleted(
    data: dict[str, Any],
    session: Any,
    Workspace: Any,
    select: Any,
) -> dict[str, str]:
    sub_id = data.get("id")
    ws = session.exec(
        select(Workspace).where(Workspace.stripe_subscription_id == sub_id)
    ).first()
    if not ws:
        return {"action": "skipped", "reason": "workspace_not_found"}

    ws.tier = "free"
    ws.stripe_subscription_status = "cancelled"
    ws.stripe_subscription_id = None
    ws.stripe_price_id = None

    session.add(ws)
    session.commit()
    return {"action": "downgraded_to_free"}


def _handle_invoice_paid(
    data: dict[str, Any],
    session: Any,
    Workspace: Any,
    select: Any,
) -> dict[str, str]:
    """Reset monthly usage counters on each successful billing cycle."""
    customer_id = data.get("customer")
    ws = session.exec(
        select(Workspace).where(Workspace.stripe_customer_id == customer_id)
    ).first()
    if not ws:
        return {"action": "skipped", "reason": "workspace_not_found"}

    ws.domain_lookups_used = 0
    ws.export_credits_used = 0
    ws.api_calls_used = 0
    ws.billing_cycle_start = datetime.now(timezone.utc)

    session.add(ws)
    session.commit()
    return {"action": "usage_reset"}


def _handle_invoice_payment_failed(
    data: dict[str, Any],
    session: Any,
    Workspace: Any,
    select: Any,
) -> dict[str, str]:
    customer_id = data.get("customer")
    ws = session.exec(
        select(Workspace).where(Workspace.stripe_customer_id == customer_id)
    ).first()
    if not ws:
        return {"action": "skipped", "reason": "workspace_not_found"}

    ws.stripe_subscription_status = "past_due"
    session.add(ws)
    session.commit()
    return {"action": "marked_past_due"}
