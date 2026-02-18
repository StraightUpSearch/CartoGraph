"""
Workspaces API — /api/v1/workspaces

Manages team workspaces, subscription tiers, and workspace-scoped API tokens.
One workspace per user for now (multi-workspace support in Phase 5).

API token flow:
  POST /workspaces/{id}/token       — rotate token; returns plaintext once only
  GET  /workspaces/{id}/usage       — current month usage counters
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.core.security import get_password_hash
from app.models import Workspace, WorkspaceCreate, WorkspacePublic

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

_TOKEN_PREFIX = "cg_"


def _generate_api_token() -> tuple[str, str, str]:
    """
    Generate a workspace API token.
    Returns (plaintext_token, hashed_token, display_prefix).
    The plaintext is shown once; only the hash is stored.
    """
    raw = secrets.token_urlsafe(48)
    plaintext = f"{_TOKEN_PREFIX}{raw}"
    hashed = get_password_hash(plaintext)
    prefix = plaintext[:12]  # "cg_" + first 9 chars for display
    return plaintext, hashed, prefix


@router.get("/", response_model=list[WorkspacePublic])
def list_workspaces(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[WorkspacePublic]:
    """List workspaces owned by the current user."""
    workspaces = session.exec(
        select(Workspace).where(Workspace.owner_id == current_user.id)
    ).all()
    return [WorkspacePublic.model_validate(w, from_attributes=True) for w in workspaces]


@router.post("/", response_model=WorkspacePublic, status_code=201)
def create_workspace(
    payload: WorkspaceCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> WorkspacePublic:
    """Create a new workspace (defaults to Free tier)."""
    workspace = Workspace(
        name=payload.name,
        owner_id=current_user.id,
        tier="free",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return WorkspacePublic.model_validate(workspace, from_attributes=True)


@router.get("/{workspace_id}", response_model=WorkspacePublic)
def get_workspace(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> WorkspacePublic:
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    return WorkspacePublic.model_validate(ws, from_attributes=True)


@router.post("/{workspace_id}/token")
def rotate_api_token(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """
    Generate a new workspace API token.
    The full token is returned ONCE and never stored in plaintext.
    Previous token is invalidated immediately.
    """
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    plaintext, hashed, prefix = _generate_api_token()
    ws.api_token_hash = hashed
    ws.api_token_prefix = prefix
    session.add(ws)
    session.commit()
    return {
        "token": plaintext,
        "prefix": prefix,
        "warning": "Store this token securely — it will not be shown again.",
    }


@router.get("/{workspace_id}/usage")
def get_usage(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Return current-month usage counters and limits for this workspace."""
    from app.tier_gating import TIER_LIMITS

    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    limits = TIER_LIMITS.get(ws.tier, TIER_LIMITS["free"])
    return {
        "tier": ws.tier,
        "billing_cycle_start": ws.billing_cycle_start,
        "domain_lookups": {
            "used": ws.domain_lookups_used,
            "limit": limits.max_lookups_per_month,
        },
        "export_credits": {
            "used": ws.export_credits_used,
            "limit": limits.max_export_credits_per_month,
        },
        "api_calls": {
            "used": ws.api_calls_used,
            "limit": limits.max_api_calls_per_month,
        },
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _get_owned_workspace(
    workspace_id: uuid.UUID,
    session: Session,
    user_id: uuid.UUID,
) -> Workspace:
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if ws.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return ws
