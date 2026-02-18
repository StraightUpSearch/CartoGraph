"""
Domains API — /api/v1/domains

Endpoints:
  GET  /domains            — paginated list with filter parameters
  GET  /domains/{id}       — full domain profile
  POST /domains/import     — bulk domain import (triggers enrichment pipeline)
  GET  /domains/stats      — dashboard summary statistics

Tier gating: implemented as TODO middleware stubs. Field masking by tier
will be added in Phase 3 when Stripe billing is wired up.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, text
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Domain, DomainPublic, DomainsPublic, DomainSummary

router = APIRouter(prefix="/domains", tags=["domains"])


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
        confidence_value=(confidence.get("value")),
    )


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
    # New this week
    new_this_week = session.exec(
        select(func.count())
        .select_from(Domain)
        .where(
            text(
                "first_seen_at >= NOW() - INTERVAL '7 days'"
            )
        )
    ).one()
    return {
        "total_domains": total,
        "active_domains": active,
        "new_this_week": new_this_week,
    }


@router.get("/", response_model=DomainsPublic)
def list_domains(
    session: SessionDep,
    _current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
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

    All filters are AND-combined. JSONB filters use PostgreSQL expression indexes
    created in the Alembic migration. For large result sets use cursor pagination
    (cursor by domain_id) — this page-based endpoint is for the dashboard UI.
    """
    stmt = select(Domain)

    if country:
        stmt = stmt.where(Domain.country == country.upper())
    if status:
        stmt = stmt.where(Domain.status == status)
    if platform:
        stmt = stmt.where(
            text("(ecommerce->>'platform') = :platform").bindparams(
                platform=platform
            )
        )
    if category:
        stmt = stmt.where(
            text(
                "(ecommerce->>'category_primary') ILIKE :category"
            ).bindparams(category=f"%{category}%")
        )
    if min_dr is not None:
        stmt = stmt.where(
            text(
                "(seo_metrics->>'domain_rating')::int >= :min_dr"
            ).bindparams(min_dr=min_dr)
        )
    if max_dr is not None:
        stmt = stmt.where(
            text(
                "(seo_metrics->>'domain_rating')::int <= :max_dr"
            ).bindparams(max_dr=max_dr)
        )
    if min_traffic is not None:
        stmt = stmt.where(
            text(
                "(seo_metrics->>'organic_traffic_estimate')::int >= :min_traffic"
            ).bindparams(min_traffic=min_traffic)
        )
    if min_intent is not None:
        stmt = stmt.where(
            text(
                "(intent_layer->>'commercial_intent_score')::int >= :min_intent"
            ).bindparams(min_intent=min_intent)
        )
    if shopping_carousel is not None:
        val = "true" if shopping_carousel else "false"
        stmt = stmt.where(
            text(
                f"(serp_intelligence->'serp_features'->>'shopping_carousel')::boolean = {val}"
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.exec(count_stmt).one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Domain.last_updated_at.desc()).offset(offset).limit(page_size)  # type: ignore[attr-defined]
    domains = session.exec(stmt).all()

    return DomainsPublic(
        data=[_extract_summary(d) for d in domains],
        count=total,
        page=page,
    )


@router.get("/{domain_id}", response_model=DomainPublic)
def get_domain(
    domain_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentUser,
) -> DomainPublic:
    """Full domain profile with all enrichment JSONB fields."""
    domain = session.get(Domain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    return DomainPublic.model_validate(domain, from_attributes=True)


@router.get("/by-name/{domain_name}", response_model=DomainPublic)
def get_domain_by_name(
    domain_name: str,
    session: SessionDep,
    _current_user: CurrentUser,
) -> DomainPublic:
    """Look up a domain by its hostname (e.g. example.co.uk)."""
    domain = session.exec(
        select(Domain).where(Domain.domain == domain_name.lower())
    ).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    return DomainPublic.model_validate(domain, from_attributes=True)


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

        # Create stub record — pipeline will populate JSONB fields
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

        # Queue for immediate classification
        classify_domain_task.delay(domain=raw_domain)
        queued += 1

    session.commit()
    return {
        "status": "accepted",
        "created": created,
        "queued_for_enrichment": queued,
        "skipped_existing": skipped,
    }
