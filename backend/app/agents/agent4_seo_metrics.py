"""
Agent 4: SEO Metrics Enrichment

Populates domain_rating, domain_authority, traffic estimates, backlink counts,
referring domain counts, and organic keyword counts.

Data sources:
  - DataForSEO Backlinks API (primary) — DR, backlinks, referring domains, traffic
  - Moz Links API (supplementary) — DA, PA, Spam Score

Schedule: Weekly for top 20% of domains by traffic; bi-weekly for the rest.
Cost:      ~£0.03 per domain per full cycle (DataForSEO + Moz combined)

Cross-validation: flag where DataForSEO DR and Moz DA diverge by > 30 points.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.agents.sources.base import BacklinkResult, DataSource
from app.agents.sources.dataforseo import DataForSEOSource
from app.agents.sources.moz import MozSource
from app.celery_app import celery_app
from app.config.variables import cg_settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class SeoMetricsOutput(BaseModel):
    job_id: str
    agent: str = "agent4_seo_metrics"
    schema_version: str = cg_settings.SCHEMA_VERSION
    domain: str
    # Primary metrics (DataForSEO)
    domain_rating: int | None = None
    referring_domains_count: int | None = None
    backlinks_count: int | None = None
    organic_traffic_estimate: int | None = None
    organic_keywords_count: int | None = None
    organic_traffic_trend: str | None = None  # growing | stable | declining
    # Supplementary metrics (Moz)
    domain_authority: int | None = None
    page_authority: int | None = None
    spam_score: int | None = None
    # Quality flags
    authority_divergence_flagged: bool = False  # DR vs DA differ by > 30
    low_traffic_flagged: bool = False            # organic_traffic_estimate < 10/mo
    high_spam_flagged: bool = False             # spam_score > 60
    # Provenance
    sources_used: list[str] = Field(default_factory=list)
    as_of: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Core enrichment logic
# ---------------------------------------------------------------------------


def _merge_backlink_results(
    dfs_result: BacklinkResult | None,
    moz_result: BacklinkResult | None,
) -> SeoMetricsOutput:
    """Merge DataForSEO and Moz results into a single SeoMetricsOutput."""
    out = SeoMetricsOutput(
        job_id="inline",
        domain=dfs_result.domain if dfs_result else (moz_result.domain if moz_result else ""),
    )

    if dfs_result:
        out.domain_rating = dfs_result.domain_rating
        out.referring_domains_count = dfs_result.referring_domains_count
        out.backlinks_count = dfs_result.backlinks_count
        out.organic_traffic_estimate = dfs_result.organic_traffic_estimate
        out.organic_keywords_count = dfs_result.organic_keywords_count
        out.sources_used.append(dfs_result.source)

    if moz_result:
        out.domain_authority = moz_result.domain_authority
        out.page_authority = moz_result.page_authority
        out.spam_score = moz_result.spam_score
        out.sources_used.append(moz_result.source)

    # Quality flags
    if (
        out.domain_rating is not None
        and out.domain_authority is not None
        and abs(out.domain_rating - out.domain_authority) > 30
    ):
        out.authority_divergence_flagged = True
        log.warning(
            "Authority divergence for %s: DR=%d DA=%d",
            out.domain,
            out.domain_rating,
            out.domain_authority,
        )

    if out.organic_traffic_estimate is not None and out.organic_traffic_estimate < 10:
        out.low_traffic_flagged = True

    if out.spam_score is not None and out.spam_score > 60:
        out.high_spam_flagged = True

    return out


async def enrich_domain_seo(
    domain: str,
    primary_source: DataSource | None = None,
    supplementary_source: DataSource | None = None,
    job_id: str = "manual",
) -> SeoMetricsOutput:
    """Enrich a single domain with SEO metrics from DataForSEO + Moz."""
    if primary_source is None:
        primary_source = DataForSEOSource()
    if supplementary_source is None:
        supplementary_source = MozSource()

    dfs_results = await primary_source.get_backlink_metrics([domain])
    dfs = dfs_results[0] if dfs_results else None

    moz_results: list[BacklinkResult] = []
    try:
        moz_results = await supplementary_source.get_backlink_metrics([domain])
    except Exception as exc:
        # Moz is supplementary — don't fail the whole task if it's down
        log.warning("Moz API failed for %s: %s", domain, exc)

    moz = moz_results[0] if moz_results else None
    result = _merge_backlink_results(dfs, moz)
    result.job_id = job_id
    return result


async def enrich_batch(
    domains: list[str],
    job_id: str = "manual",
) -> list[SeoMetricsOutput]:
    """Enrich a batch of domains. Returns one output per domain."""
    primary = DataForSEOSource()
    supplementary = MozSource()

    # DataForSEO supports batch requests — more efficient than one-by-one
    dfs_results = await primary.get_backlink_metrics(domains)
    dfs_by_domain = {r.domain: r for r in dfs_results}

    outputs: list[SeoMetricsOutput] = []
    for domain in domains:
        moz_results: list[BacklinkResult] = []
        try:
            moz_results = await supplementary.get_backlink_metrics([domain])
        except Exception:
            pass
        moz = moz_results[0] if moz_results else None
        out = _merge_backlink_results(dfs_by_domain.get(domain), moz)
        out.job_id = job_id
        outputs.append(out)

    return outputs


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent4_seo_metrics.run_seo_metrics",
    bind=True,
    max_retries=5,
    queue="agent4_seo_metrics",
)
def run_seo_metrics(
    self: Task,
    domains: list[str],
) -> list[dict[str, Any]]:
    """
    Celery task entry point for Agent 4.

    Accepts a batch of domains, enriches each with DataForSEO + Moz,
    and returns a list of SeoMetricsOutput dicts (one per domain).
    """
    import asyncio

    job_id = str(self.request.id or "local")
    try:
        results = asyncio.get_event_loop().run_until_complete(
            enrich_batch(domains=domains, job_id=job_id)
        )
        return [r.model_dump() for r in results]
    except Exception as exc:
        log.exception("Agent 4 failed for job %s: %s", job_id, exc)
        countdown = 60 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
