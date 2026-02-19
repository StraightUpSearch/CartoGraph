"""
Billing API — /api/v1/billing

Endpoints:
  GET  /billing/plans              — public plan catalogue + founding member seat count
  POST /billing/checkout/{price_id} — create Stripe checkout session (authenticated)
  GET  /billing/portal             — create Stripe billing portal session (authenticated)
  POST /billing/webhook            — Stripe webhook receiver (no JWT auth, Stripe-Signature)

The webhook endpoint is intentionally excluded from JWT authentication because
Stripe signs payloads with a webhook secret, which is verified by construct_webhook_event().
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlmodel import Session

from app.api.deps import CurrentUser, SessionDep
from app.stripe_billing import (
    PLAN_CATALOGUE,
    construct_webhook_event,
    create_billing_portal_session,
    create_checkout_session,
    get_founding_member_count,
    process_webhook_event,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Public — plan catalogue
# ---------------------------------------------------------------------------


@router.get("/plans")
def list_plans(session: SessionDep) -> dict[str, object]:
    """
    Return the public plan catalogue plus the current founding member seat count.
    No authentication required — used by the pricing page.
    """
    founding_count = get_founding_member_count(session)
    from app.config.variables import cg_settings

    return {
        "plans": PLAN_CATALOGUE,
        "founding_member": {
            "count": founding_count,
            "cap": cg_settings.FOUNDING_MEMBER_CAP,
            "available": max(0, cg_settings.FOUNDING_MEMBER_CAP - founding_count),
        },
    }


# ---------------------------------------------------------------------------
# Authenticated — checkout + portal
# ---------------------------------------------------------------------------


@router.post("/checkout/{price_id}")
def start_checkout(
    price_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """
    Create a Stripe Checkout Session for the given price_id.
    Returns { "url": "<stripe_checkout_url>" }.
    """
    from sqlmodel import select

    from app.models import Workspace
    from app.stripe_billing import get_stripe_price_to_tier_map as _tier_map_fn
    from app.config.variables import cg_settings

    # Verify the price_id maps to a known tier
    tier_map = _tier_map_fn()
    if price_id not in tier_map:
        raise HTTPException(status_code=400, detail="Unknown price_id")

    # Get caller's workspace
    ws = session.exec(
        select(Workspace).where(Workspace.owner_id == current_user.id)
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    is_founding = price_id == cg_settings.STRIPE_PRICE_PRO_FOUNDING

    # Check founding member cap before starting checkout
    if is_founding:
        founding_count = get_founding_member_count(session)
        if founding_count >= cg_settings.FOUNDING_MEMBER_CAP:
            raise HTTPException(
                status_code=409,
                detail="Founding Member programme is full (200 seats taken).",
            )

    try:
        url = create_checkout_session(
            price_id=price_id,
            stripe_customer_id=ws.stripe_customer_id,
            workspace_id=str(ws.workspace_id),
            user_email=current_user.email,
            is_founding_member_price=is_founding,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"url": url}


@router.get("/portal")
def billing_portal(
    session: SessionDep,
    current_user: CurrentUser,
    return_url: str | None = None,
) -> dict[str, str]:
    """
    Create a Stripe Billing Portal session for the current user's workspace.
    Returns { "url": "<stripe_portal_url>" }.
    """
    from sqlmodel import select

    from app.models import Workspace

    ws = session.exec(
        select(Workspace).where(Workspace.owner_id == current_user.id)
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not ws.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription. Subscribe via /billing/checkout first.",
        )

    try:
        url = create_billing_portal_session(
            stripe_customer_id=ws.stripe_customer_id,
            return_url=return_url,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"url": url}


# ---------------------------------------------------------------------------
# Stripe webhook — no JWT auth
# ---------------------------------------------------------------------------


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    session: SessionDep,
    stripe_signature: str = Header(alias="stripe-signature", default=""),
) -> dict[str, str]:
    """
    Receive Stripe webhook events.

    Authentication: Stripe-Signature header (HMAC-SHA256 verified by Stripe SDK).
    This endpoint must NOT be behind JWT auth middleware.
    """
    payload = await request.body()

    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        import stripe as _stripe

        event = construct_webhook_event(payload, stripe_signature)
    except ValueError as exc:
        # Invalid payload
        log.warning("stripe webhook: invalid payload — %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload") from exc
    except Exception as exc:
        # Signature verification failed
        log.warning("stripe webhook: signature verification failed — %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    result = process_webhook_event(event, session)
    log.info("stripe webhook result: %s", result)
    return result
