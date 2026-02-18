"""
Agent 2: SERP Discovery

Discovers new UK ecommerce domains by querying SERPs for commercial-intent
keywords. Also captures SERP feature presence per query.

Schedule: Daily (rotating keyword batches; full set cycles every 7 days).
Data source: DataForSEO queued mode — TaskPost → TaskReady → TaskGet

Pipeline:
  1. Load keyword batch from queue (500–1,000 queries per run)
  2. Submit to DataForSEO queued endpoint (google.co.uk, UK geo)
  3. Parse organic results positions 1–30
  4. Extract unique domains; flag new ones for enrichment
  5. Record SERP features present per query
  6. Update serp_intelligence fields for known domains

Output: JSON-serialisable SerpDiscoveryOutput Pydantic model.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.agents.sources.base import DataSource, SerpResult
from app.agents.sources.dataforseo import DataForSEOSource
from app.celery_app import celery_app
from app.config.variables import cg_settings

log = logging.getLogger(__name__)

# Domains excluded from discovery — marketplace listing pages only, not the
# marketplaces themselves (they are legitimate ecommerce domains in the DB).
_EXCLUDED_DOMAIN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"amazon\.(co\.uk|com)$"),
    re.compile(r"ebay\.(co\.uk|com)$"),
    re.compile(r"etsy\.com$"),
    re.compile(r"google\.(co\.uk|com)$"),
    re.compile(r"facebook\.com$"),
    re.compile(r"instagram\.com$"),
    re.compile(r"youtube\.com$"),
    re.compile(r"pinterest\.(co\.uk|com)$"),
    re.compile(r"wikipedia\.org$"),
    re.compile(r"reddit\.com$"),
    re.compile(r"trustpilot\.com$"),
]

# UK relevance: accept .co.uk, .uk TLDs; or .com that may be UK-operated
_UK_TLD_PATTERN = re.compile(r"\.(co\.uk|org\.uk|me\.uk|uk)$")


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class DiscoveredDomain(BaseModel):
    domain: str
    tld: str | None = None
    discovery_keyword: str
    discovery_position: int
    serp_features: dict[str, bool] = Field(default_factory=dict)
    is_new: bool = True
    first_seen_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "dataforseo_serp"
    raw_payload_hash: str | None = None


class SerpDiscoveryOutput(BaseModel):
    job_id: str
    agent: str = "agent2_serp_discovery"
    schema_version: str = cg_settings.SCHEMA_VERSION
    country: str = cg_settings.DEFAULT_COUNTRY
    run_at: str
    keywords_processed: int
    domains_discovered: list[DiscoveredDomain]
    new_domain_count: int
    known_domain_count: int
    excluded_count: int


# ---------------------------------------------------------------------------
# Core discovery logic
# ---------------------------------------------------------------------------


def _extract_tld(domain: str) -> str | None:
    m = re.search(r"\.[a-z]{2,}(\.[a-z]{2,})?$", domain)
    return m.group(0) if m else None


def _is_excluded(domain: str) -> bool:
    return any(p.search(domain) for p in _EXCLUDED_DOMAIN_PATTERNS)


def _is_uk_relevant(domain: str) -> bool:
    """Accept .co.uk/.uk TLDs as UK-relevant; .com domains need further validation."""
    return bool(_UK_TLD_PATTERN.search(domain)) or domain.endswith(".com")


def process_serp_results(
    results: list[SerpResult],
    known_domains: set[str],
) -> tuple[list[DiscoveredDomain], int]:
    """
    De-duplicate and filter SERP results into DiscoveredDomain records.
    Returns (discovered_domains, excluded_count).
    """
    seen: set[str] = set()
    discovered: list[DiscoveredDomain] = []
    excluded = 0

    for r in results:
        domain = r.domain.lower().strip()
        if not domain or domain in seen:
            continue
        seen.add(domain)

        if _is_excluded(domain):
            excluded += 1
            continue

        if not _is_uk_relevant(domain):
            excluded += 1
            continue

        discovered.append(
            DiscoveredDomain(
                domain=domain,
                tld=_extract_tld(domain),
                discovery_keyword=r.keyword,
                discovery_position=r.position,
                serp_features=r.serp_features,
                is_new=domain not in known_domains,
                source=r.source,
                raw_payload_hash=r.raw_payload_hash,
            )
        )

    return discovered, excluded


async def run_discovery(
    keywords: list[str],
    source: DataSource | None = None,
    known_domains: set[str] | None = None,
    job_id: str = "manual",
) -> SerpDiscoveryOutput:
    """
    Core async discovery logic — can be called directly for testing.
    """
    if source is None:
        source = DataForSEOSource()
    if known_domains is None:
        known_domains = set()

    log.info("Agent 2 starting SERP discovery for %d keywords", len(keywords))

    task_ids = await source.submit_serp_tasks(
        keywords=keywords,
        geo=cg_settings.SERP_DISCOVERY_GEO,
        language=cg_settings.SERP_DISCOVERY_LANGUAGE,
    )
    serp_results = await source.get_serp_results(task_ids)
    discovered, excluded_count = process_serp_results(serp_results, known_domains)

    new_count = sum(1 for d in discovered if d.is_new)
    known_count = len(discovered) - new_count

    log.info(
        "Agent 2 found %d domains (%d new, %d known, %d excluded)",
        len(discovered),
        new_count,
        known_count,
        excluded_count,
    )

    return SerpDiscoveryOutput(
        job_id=job_id,
        run_at=datetime.now(timezone.utc).isoformat(),
        keywords_processed=len(keywords),
        domains_discovered=discovered,
        new_domain_count=new_count,
        known_domain_count=known_count,
        excluded_count=excluded_count,
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent2_serp_discovery.run_serp_discovery",
    bind=True,
    max_retries=5,
    queue="agent2_serp_discovery",
)
def run_serp_discovery(
    self: Task,
    keywords: list[str],
    known_domains: list[str] | None = None,
) -> dict[str, Any]:
    """
    Celery task entry point for Agent 2.

    `known_domains` is the set of domains already in the database — passed by
    the orchestrator so Agent 2 can flag new vs known discoveries.
    """
    import asyncio

    job_id = str(self.request.id or "local")
    known = set(known_domains or [])

    try:
        result = asyncio.get_event_loop().run_until_complete(
            run_discovery(
                keywords=keywords,
                known_domains=known,
                job_id=job_id,
            )
        )
        return result.model_dump()
    except Exception as exc:
        log.exception("Agent 2 failed for job %s: %s", job_id, exc)
        # Exponential backoff: 60s, 120s, 240s, 480s, 960s
        countdown = 60 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
