"""
Domains API — /api/v1/domains

Endpoints:
  GET  /domains            — paginated list with filter parameters + cursor pagination
  GET  /domains/stats      — dashboard summary statistics
  GET  /domains/{id}       — full domain profile (tier-masked)
  GET  /domains/by-name/{name} — look up by hostname (tier-masked)
  POST /domains/import     — bulk domain import (triggers enrichment pipeline)

Tier gating:
  - Row limits clamped to the caller's workspace tier via TierGate.
  - Full domain profiles are masked via mask_domain_by_tier().
  - Lookup counter incremented on individual domain fetches.
  - Caller's workspace is resolved from the first workspace they own.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, text
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Domain, DomainPublic, DomainsPublic, DomainSummary, Workspace
from app.tier_gating import TierGate, mask_domain_by_tier

router = APIRouter(prefix="/domains", tags=["domains"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_caller_workspace(session: Session, user_id: uuid.UUID) -> Workspace | None:
    """Return the first workspace owned by the user, or None."""
    return session.exec(
        select(Workspace).where(Workspace.owner_id == user_id)
    ).first()


def _extract_summary(domain: Domain) -> DomainSummary:
    """Project scalar fields out of JSONB columns for the list view."""
    seo = domain.seo_metrics or {}
    intent = domain.intent_layer or {}
    ecom = domain.ecommerce or {}
    confidence = domain.confidence_score or {}
    return DomainSummary(
        domain_id=domain.domain_id,
        domain=domain.domain,
        country=domain.country,
        tld=domain.tld,
        status=domain.status,
        first_seen_at=domain.first_seen_at,
        last_updated_at=domain.last_updated_at,
        schema_version=domain.schema_version,
        domain_rating=seo.get("domain_rating"),
        organic_traffic_estimate=seo.get("organic_traffic_estimate"),
        commercial_intent_score=intent.get("commercial_intent_score"),
        platform=ecom.get("platform"),
        category_primary=ecom.get("category_primary"),
        confidence_value=confidence.get("value"),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_domain_stats(
    session: SessionDep,
    _current_user: CurrentUser,
) -> dict[str, Any]:
    """Dashboard summary statistics."""
    total = session.exec(select(func.count()).select_from(Domain)).one()
    active = session.exec(
        select(func.count())
        .select_from(Domain)
        .where(Domain.status == "active")
    ).one()
    new_this_week = session.exec(
        select(func.count())
        .select_from(Domain)
        .where(text("first_seen_at >= NOW() - INTERVAL '7 days'"))
    ).one()
    return {
        "total_domains": total,
        "active_domains": active,
        "new_this_week": new_this_week,
    }


@router.get("/", response_model=DomainsPublic)
def list_domains(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    # Cursor pagination — use instead of page for large result sets
    after_cursor: str | None = Query(
        default=None,
        description="Cursor for next-page fetch. Use next_cursor from previous response.",
    ),
    country: str | None = Query(default=None),
    status: str | None = Query(default=None, description="active | inactive | pending"),
    platform: str | None = Query(default=None, description="e.g. Shopify, WooCommerce"),
    category: str | None = Query(default=None, description="Primary product category"),
    min_dr: int | None = Query(default=None, ge=0, le=100),
    max_dr: int | None = Query(default=None, ge=0, le=100),
    min_traffic: int | None = Query(default=None, ge=0),
    min_intent: int | None = Query(default=None, ge=1, le=10),
    shopping_carousel: bool | None = Query(default=None),
) -> DomainsPublic:
    """
    List domains with optional filter parameters.

    Supports both offset (page/page_size) and cursor (after_cursor) pagination.
    Cursor pagination is preferred for large result sets — it is stable against
    concurrent inserts. The cursor is an opaque string encoding the last-seen
    domain_id; pass next_cursor from the previous response as after_cursor.

    Row limits are enforced by the caller's workspace tier.
    """
    ws = _get_caller_workspace(session, current_user.id)
    tier = ws.tier if ws else "free"
    gate = TierGate(tier)
    effective_page_size = gate.clamp_page_size(page_size)

    stmt = select(Domain)

    if country:
        stmt = stmt.where(Domain.country == country.upper())
    if status:
        stmt = stmt.where(Domain.status == status)
    if platform:
        stmt = stmt.where(
            text("(ecommerce->>'platform') = :platform").bindparams(platform=platform)
        )
    if category:
        stmt = stmt.where(
            text("(ecommerce->>'category_primary') ILIKE :category").bindparams(
                category=f"%{category}%"
            )
        )
    if min_dr is not None:
        stmt = stmt.where(
            text("(seo_metrics->>'domain_rating')::int >= :min_dr").bindparams(min_dr=min_dr)
        )
    if max_dr is not None:
        stmt = stmt.where(
            text("(seo_metrics->>'domain_rating')::int <= :max_dr").bindparams(max_dr=max_dr)
        )
    if min_traffic is not None:
        stmt = stmt.where(
            text("(seo_metrics->>'organic_traffic_estimate')::int >= :min_traffic").bindparams(
                min_traffic=min_traffic
            )
        )
    if min_intent is not None:
        stmt = stmt.where(
            text("(intent_layer->>'commercial_intent_score')::int >= :min_intent").bindparams(
                min_intent=min_intent
            )
        )
    if shopping_carousel is not None:
        val = "true" if shopping_carousel else "false"
        stmt = stmt.where(
            text(
                f"(serp_intelligence->'serp_features'->>'shopping_carousel')::boolean = {val}"
            )
        )

    # Cursor pagination: filter to rows after the cursor domain_id
    if after_cursor:
        try:
            cursor_id = uuid.UUID(after_cursor)
            stmt = stmt.where(Domain.domain_id > cursor_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor value")

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.exec(count_stmt).one()

    # Offset pagination applies only when cursor is not used
    if not after_cursor:
        offset = (page - 1) * effective_page_size
        stmt = stmt.order_by(Domain.domain_id.asc()).offset(offset)  # type: ignore[attr-defined]
    else:
        stmt = stmt.order_by(Domain.domain_id.asc())  # type: ignore[attr-defined]

    stmt = stmt.limit(effective_page_size)
    domains = session.exec(stmt).all()

    # Build next cursor from the last domain_id in this page
    next_cursor: str | None = None
    if len(domains) == effective_page_size:
        next_cursor = str(domains[-1].domain_id)

    return DomainsPublic(
        data=[_extract_summary(d) for d in domains],
        count=total,
        page=page,
        next_cursor=next_cursor,
    )


@router.get("/{domain_id}", response_model=DomainPublic)
def get_domain(
    domain_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> DomainPublic:
    """
    Full domain profile with all enrichment JSONB fields.
    Fields are masked according to the caller's workspace tier.
    Increments the monthly domain lookup counter.
    """
    ws = _get_caller_workspace(session, current_user.id)
    tier = ws.tier if ws else "free"
    gate = TierGate(tier)

    # Enforce lookup quota (only when a workspace exists)
    if ws:
        gate.check_lookup_quota(ws.domain_lookups_used)

    domain = session.get(Domain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Increment lookup counter
    if ws:
        ws.domain_lookups_used += 1
        session.add(ws)
        session.commit()

    raw = DomainPublic.model_validate(domain, from_attributes=True).model_dump()
    masked = mask_domain_by_tier(raw, tier)
    return DomainPublic.model_validate(masked)


@router.get("/by-name/{domain_name}", response_model=DomainPublic)
def get_domain_by_name(
    domain_name: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> DomainPublic:
    """
    Look up a domain by its hostname (e.g. example.co.uk).
    Increments the monthly domain lookup counter.
    """
    ws = _get_caller_workspace(session, current_user.id)
    tier = ws.tier if ws else "free"
    gate = TierGate(tier)

    if ws:
        gate.check_lookup_quota(ws.domain_lookups_used)

    domain = session.exec(
        select(Domain).where(Domain.domain == domain_name.lower())
    ).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    if ws:
        ws.domain_lookups_used += 1
        session.add(ws)
        session.commit()

    raw = DomainPublic.model_validate(domain, from_attributes=True).model_dump()
    masked = mask_domain_by_tier(raw, tier)
    return DomainPublic.model_validate(masked)


@router.post("/import", status_code=202)
def import_domains(
    payload: list[dict[str, Any]],
    session: SessionDep,
    _current_user: CurrentUser,
) -> dict[str, Any]:
    """
    Bulk domain import. Accepts a list of {domain, tags?} objects.
    Creates stub records then queues them through the enrichment pipeline.

    Returns immediately (202 Accepted) — enrichment runs asynchronously.
    """
    from app.agents.agent3_domain_classifier import classify_domain_task

    created = 0
    queued = 0
    skipped = 0

    for item in payload:
        raw_domain = (item.get("domain") or "").lower().strip()
        if not raw_domain:
            skipped += 1
            continue

        existing = session.exec(
            select(Domain).where(Domain.domain == raw_domain)
        ).first()
        if existing:
            skipped += 1
            continue

        tld = raw_domain.split(".")[-1] if "." in raw_domain else None
        full_tld = f".{tld}" if tld else None
        domain_obj = Domain(
            domain=raw_domain,
            tld=full_tld,
            status="pending",
            discovery={"method": "bulk_import", "tags": item.get("tags", [])},
        )
        session.add(domain_obj)
        created += 1

        classify_domain_task.delay(domain=raw_domain)
        queued += 1

    session.commit()
    return {
        "status": "accepted",
        "created": created,
        "queued_for_enrichment": queued,
        "skipped_existing": skipped,
    }
