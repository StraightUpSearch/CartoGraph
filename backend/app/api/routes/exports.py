"""
Exports API — /api/v1/workspaces/{workspace_id}/exports/domains

Generates CSV exports from the domain database. Each export costs one
export credit (tracked on the Workspace record). Credit limits are
enforced per billing cycle by the tier gating layer.

Endpoints:
  POST /workspaces/{id}/exports/domains — generate and stream a CSV file

CSV columns are determined by the workspace tier:
  Free/Starter  — basic scalar fields only
  Professional+ — all unmasked enrichment fields flattened

Query filters mirror GET /domains for consistency.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.workspaces import _get_owned_workspace
from app.models import Domain
from app.tier_gating import TierGate, mask_domain_by_tier

router = APIRouter(tags=["exports"])

# Columns always included in every export
_BASE_COLUMNS = [
    "domain", "country", "tld", "status", "first_seen_at", "last_updated_at",
]

# Additional flat columns from JSONB for all tiers with access
_SEO_COLUMNS = ["domain_rating", "domain_authority", "organic_traffic_estimate",
                "referring_domains_count", "spam_score"]
_INTENT_COLUMNS = ["commercial_intent_score"]
_ECOM_COLUMNS = ["platform", "category_primary", "product_count_estimate"]


def _flatten_domain(domain: Domain, tier: str) -> dict[str, str]:
    """
    Flatten a Domain record into a flat string dict for CSV output,
    applying tier-appropriate field masking.
    """
    domain_dict = {
        "domain_id": str(domain.domain_id),
        "domain": domain.domain,
        "country": domain.country,
        "tld": domain.tld or "",
        "status": domain.status,
        "first_seen_at": domain.first_seen_at.isoformat(),
        "last_updated_at": domain.last_updated_at.isoformat(),
        "schema_version": domain.schema_version,
        # JSONB groups
        "discovery": domain.discovery,
        "ecommerce": domain.ecommerce,
        "seo_metrics": domain.seo_metrics,
        "intent_layer": domain.intent_layer,
        "serp_intelligence": domain.serp_intelligence,
        "technical_layer": domain.technical_layer,
        "contact": domain.contact,
        "marketplace_overlap": domain.marketplace_overlap,
        "paid_ads_presence": domain.paid_ads_presence,
        "meta": domain.meta,
        "change_tracking": domain.change_tracking,
        "confidence_score": domain.confidence_score,
        "pipeline": domain.pipeline,
        "ai_summary": domain.ai_summary,
    }

    masked = mask_domain_by_tier(domain_dict, tier)

    # Flatten JSONB groups into dot-prefixed columns
    flat: dict[str, str] = {}
    for key in ["domain_id", "domain", "country", "tld", "status",
                "first_seen_at", "last_updated_at", "schema_version"]:
        flat[key] = str(masked.get(key) or "")

    jsonb_groups = [
        "discovery", "ecommerce", "seo_metrics", "intent_layer",
        "serp_intelligence", "technical_layer", "contact",
        "marketplace_overlap", "paid_ads_presence", "meta",
        "change_tracking", "confidence_score",
    ]
    for group in jsonb_groups:
        blob = masked.get(group)
        gated = masked.get(f"{group}_gated", False)
        if gated or blob is None:
            flat[group] = "[upgrade to access]" if gated else ""
        elif isinstance(blob, dict):
            for subkey, val in blob.items():
                flat[f"{group}.{subkey}"] = str(val) if val is not None else ""
        else:
            flat[group] = str(blob)

    return flat


def _iter_csv(rows: list[dict[str, str]]) -> io.StringIO:
    """Render rows as CSV string."""
    if not rows:
        return io.StringIO("")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return buf


@router.post("/workspaces/{workspace_id}/exports/domains", status_code=200)
def export_domains(
    workspace_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    # Filter params mirror /domains list endpoint
    country: str | None = Query(default=None),
    status: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    category: str | None = Query(default=None),
    min_dr: int | None = Query(default=None, ge=0, le=100),
    max_dr: int | None = Query(default=None, ge=0, le=100),
    min_traffic: int | None = Query(default=None, ge=0),
    min_intent: int | None = Query(default=None, ge=1, le=10),
    max_rows: int = Query(default=1000, ge=1, le=50_000),
) -> StreamingResponse:
    """
    Generate a CSV export of domain records filtered by the provided criteria.

    Costs one export credit per call. The credit is deducted immediately and
    the file is streamed back. If credit balance is exhausted, returns 429.

    Returns:
        StreamingResponse — text/csv with Content-Disposition attachment header.
    """
    ws = _get_owned_workspace(workspace_id, session, current_user.id)
    gate = TierGate(ws.tier)

    # Enforce export feature access and credit balance
    gate.check_export_credits(ws.export_credits_used, requested=1)

    # Clamp max_rows to the tier row limit
    effective_limit = gate.clamp_page_size(max_rows, default=1000)

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

    stmt = stmt.order_by(Domain.last_updated_at.desc()).limit(effective_limit)
    domains = session.exec(stmt).all()

    # Deduct one export credit
    ws.export_credits_used += 1
    session.add(ws)
    session.commit()

    # Flatten and render CSV
    rows = [_flatten_domain(d, ws.tier) for d in domains]
    csv_buf = _iter_csv(rows)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"cartograph_domains_{timestamp}.csv"

    return StreamingResponse(
        content=iter([csv_buf.read()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Credits-Used": str(ws.export_credits_used),
        },
    )
