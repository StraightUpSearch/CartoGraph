"""
Alerts API — /api/v1/workspaces/{workspace_id}/alerts

Manages saved alert configurations that fire when domain data crosses
a user-defined threshold. Delivery is via email, webhook, or Slack URL.

Supported alert types:
  new_domain     — a new domain matching the filter set was discovered
  tech_change    — a domain's detected tech stack changed
  dr_change      — a domain's Domain Rating changed by ≥ threshold
  serp_feature   — a domain gained or lost a SERP feature

Endpoints:
  GET    /workspaces/{id}/alerts          — list alerts
  POST   /workspaces/{id}/alerts          — create alert
  GET    /workspaces/{id}/alerts/{aid}    — get alert
  PATCH  /workspaces/{id}/alerts/{aid}    — update alert
  DELETE /workspaces/{id}/alerts/{aid}    — delete alert
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.workspaces import _get_owned_workspace
from app.models import Alert, AlertCreate, AlertPublic
from app.tier_gating import TierGate

router = APIRouter(tags=["alerts"])

_VALID_ALERT_TYPES = frozenset(
    {"new_domain", "tech_change", "dr_change", "serp_feature"}
)


def _to_public(alert: Alert) -> AlertPublic:
    return AlertPublic(
        alert_id=alert.alert_id,
        workspace_id=alert.workspace_id,
        name=alert.name,
        alert_type=alert.alert_type,
        filter_criteria=alert.filter_criteria,
        threshold=alert.threshold,
        is_active=alert.is_active,
        last_triggered=alert.last_triggered,
        created_at=alert.created_at,
    )


@router.get(
    "/workspaces/{workspace_id}/alerts",
    response_model=list[AlertPublic],
)
def list_alerts(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[AlertPublic]:
    """List all saved alerts for a workspace."""
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)
    # Free tier has 0 alerts — but listing is always allowed (returns empty)
    if gate.limits.max_alerts == 0:
        return []

    alerts = session.exec(
        select(Alert).where(Alert.workspace_id == workspace_id)
    ).all()
    return [_to_public(a) for a in alerts]


@router.post(
    "/workspaces/{workspace_id}/alerts",
    response_model=AlertPublic,
    status_code=201,
)
def create_alert(
    workspace_id: uuid.UUID,
    payload: AlertCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> AlertPublic:
    """Create a new saved alert. Enforces the per-tier alert count limit."""
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)

    if payload.alert_type not in _VALID_ALERT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid alert_type '{payload.alert_type}'. "
            f"Valid types: {sorted(_VALID_ALERT_TYPES)}",
        )

    # Enforce the per-tier alert limit
    current_count = session.exec(
        select(Alert).where(Alert.workspace_id == workspace_id)
    ).all()
    gate.check_alert_limit(len(current_count))

    alert = Alert(
        workspace_id=workspace_id,
        name=payload.name,
        alert_type=payload.alert_type,
        filter_criteria=payload.filter_criteria,
        threshold=payload.threshold,
        delivery=payload.delivery,
        is_active=True,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return _to_public(alert)


@router.get(
    "/workspaces/{workspace_id}/alerts/{alert_id}",
    response_model=AlertPublic,
)
def get_alert(
    workspace_id: uuid.UUID,
    alert_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> AlertPublic:
    _get_owned_workspace(workspace_id, session, current_user.id)
    alert = _get_owned_alert(alert_id, workspace_id, session)
    return _to_public(alert)


@router.patch(
    "/workspaces/{workspace_id}/alerts/{alert_id}",
    response_model=AlertPublic,
)
def update_alert(
    workspace_id: uuid.UUID,
    alert_id: uuid.UUID,
    payload: AlertCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> AlertPublic:
    """Replace alert configuration. All fields in AlertCreate are updated."""
    _get_owned_workspace(workspace_id, session, current_user.id)

    if payload.alert_type not in _VALID_ALERT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid alert_type '{payload.alert_type}'.",
        )

    alert = _get_owned_alert(alert_id, workspace_id, session)
    alert.name = payload.name
    alert.alert_type = payload.alert_type
    alert.filter_criteria = payload.filter_criteria
    alert.threshold = payload.threshold
    alert.delivery = payload.delivery

    session.add(alert)
    session.commit()
    session.refresh(alert)
    return _to_public(alert)


@router.patch(
    "/workspaces/{workspace_id}/alerts/{alert_id}/toggle",
    response_model=AlertPublic,
)
def toggle_alert(
    workspace_id: uuid.UUID,
    alert_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> AlertPublic:
    """Toggle the is_active flag on an alert."""
    _get_owned_workspace(workspace_id, session, current_user.id)
    alert = _get_owned_alert(alert_id, workspace_id, session)
    alert.is_active = not alert.is_active
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return _to_public(alert)


@router.delete(
    "/workspaces/{workspace_id}/alerts/{alert_id}",
    status_code=204,
)
def delete_alert(
    workspace_id: uuid.UUID,
    alert_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    _get_owned_workspace(workspace_id, session, current_user.id)
    alert = _get_owned_alert(alert_id, workspace_id, session)
    session.delete(alert)
    session.commit()


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _get_owned_alert(
    alert_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: SessionDep,
) -> Alert:
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return alert
