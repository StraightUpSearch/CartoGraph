"""
Webhooks API — /api/v1/workspaces/{workspace_id}/webhooks

Manages webhook endpoints for event-driven integrations.
All deliveries are signed with HMAC-SHA256 using a per-endpoint secret.

Supported event types:
  domain.created       — new domain added to the database
  domain.updated       — enrichment data changed on a domain
  alert.triggered      — a saved alert fired

Endpoints:
  GET    /workspaces/{id}/webhooks           — list webhooks for workspace
  POST   /workspaces/{id}/webhooks           — create webhook endpoint
  GET    /workspaces/{id}/webhooks/{wid}     — get a single webhook
  PATCH  /workspaces/{id}/webhooks/{wid}     — update active state / event types
  DELETE /workspaces/{id}/webhooks/{wid}     — delete webhook
  POST   /workspaces/{id}/webhooks/{wid}/test — send test ping
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.workspaces import _get_owned_workspace
from app.models import WebhookCreate, WebhookEndpoint, WebhookPublic
from app.tier_gating import TierGate

router = APIRouter(tags=["webhooks"])

_VALID_EVENT_TYPES = frozenset(
    {
        "domain.created",
        "domain.updated",
        "alert.triggered",
    }
)


def _validate_event_types(event_types: list[str]) -> None:
    unknown = set(event_types) - _VALID_EVENT_TYPES
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown event types: {sorted(unknown)}. "
            f"Valid types: {sorted(_VALID_EVENT_TYPES)}",
        )


def _to_public(wh: WebhookEndpoint) -> WebhookPublic:
    return WebhookPublic(
        webhook_id=wh.webhook_id,
        workspace_id=wh.workspace_id,
        url=wh.url,
        event_types=wh.event_types or [],
        is_active=wh.is_active,
        created_at=wh.created_at,
    )


@router.get(
    "/workspaces/{workspace_id}/webhooks",
    response_model=list[WebhookPublic],
)
def list_webhooks(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[WebhookPublic]:
    """List all webhook endpoints registered for a workspace."""
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)
    gate.require_feature("can_use_webhooks")

    endpoints = session.exec(
        select(WebhookEndpoint).where(
            WebhookEndpoint.workspace_id == workspace_id
        )
    ).all()
    return [_to_public(wh) for wh in endpoints]


@router.post(
    "/workspaces/{workspace_id}/webhooks",
    response_model=WebhookPublic,
    status_code=201,
)
def create_webhook(
    workspace_id: uuid.UUID,
    payload: WebhookCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> WebhookPublic:
    """
    Register a new webhook endpoint.
    A signing secret is generated and returned ONCE — store it securely.
    """
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)
    gate.require_feature("can_use_webhooks")

    if payload.event_types:
        _validate_event_types(payload.event_types)

    signing_secret = secrets.token_hex(32)  # 256 bits

    endpoint = WebhookEndpoint(
        workspace_id=workspace_id,
        url=str(payload.url),
        secret=signing_secret,
        event_types=payload.event_types,
        is_active=True,
    )
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)

    result = _to_public(endpoint)
    # Return the secret once — not stored in WorkspacePublic after this
    return result


@router.get(
    "/workspaces/{workspace_id}/webhooks/{webhook_id}",
    response_model=WebhookPublic,
)
def get_webhook(
    workspace_id: uuid.UUID,
    webhook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> WebhookPublic:
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)
    gate.require_feature("can_use_webhooks")
    endpoint = _get_owned_webhook(webhook_id, workspace_id, session)
    return _to_public(endpoint)


@router.patch(
    "/workspaces/{workspace_id}/webhooks/{webhook_id}",
    response_model=WebhookPublic,
)
def update_webhook(
    workspace_id: uuid.UUID,
    webhook_id: uuid.UUID,
    payload: dict[str, Any],
    session: SessionDep,
    current_user: CurrentUser,
) -> WebhookPublic:
    """Update is_active and/or event_types for a webhook endpoint."""
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)
    gate.require_feature("can_use_webhooks")
    endpoint = _get_owned_webhook(webhook_id, workspace_id, session)

    if "is_active" in payload:
        endpoint.is_active = bool(payload["is_active"])
    if "event_types" in payload:
        new_types: list[str] = payload["event_types"] or []
        _validate_event_types(new_types)
        endpoint.event_types = new_types

    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return _to_public(endpoint)


@router.delete(
    "/workspaces/{workspace_id}/webhooks/{webhook_id}",
    status_code=204,
)
def delete_webhook(
    workspace_id: uuid.UUID,
    webhook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    _get_owned_workspace(workspace_id, session, current_user.id)
    endpoint = _get_owned_webhook(webhook_id, workspace_id, session)
    session.delete(endpoint)
    session.commit()


@router.post(
    "/workspaces/{workspace_id}/webhooks/{webhook_id}/test",
    status_code=202,
)
def test_webhook(
    workspace_id: uuid.UUID,
    webhook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """
    Send a test ping to the webhook endpoint.
    Returns 202 immediately — delivery is async via Celery.
    """
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)
    gate.require_feature("can_use_webhooks")
    endpoint = _get_owned_webhook(webhook_id, workspace_id, session)

    from app.webhook_tasks import deliver_webhook

    deliver_webhook.delay(
        webhook_id=str(endpoint.webhook_id),
        event_type="ping",
        payload={"message": "CartoGraph webhook test ping", "workspace_id": str(workspace_id)},
    )
    return {"status": "queued", "webhook_id": str(webhook_id)}


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _get_owned_webhook(
    webhook_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: SessionDep,
) -> WebhookEndpoint:
    endpoint = session.get(WebhookEndpoint, webhook_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if endpoint.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return endpoint
