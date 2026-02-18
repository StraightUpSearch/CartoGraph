"""
DataSource — abstract provider interface

Every external data dependency (DataForSEO, Moz, Wappalyzer, etc.) implements
this interface. Agent logic is written against the abstract class only, so any
provider can be swapped without touching agent code.

Usage:
    from app.agents.sources.base import DataSource, SerpResult, BacklinkResult
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Shared result dataclasses — canonical output types agents consume
# ---------------------------------------------------------------------------


@dataclass
class SerpResult:
    """Single organic SERP result for a given keyword query."""

    keyword: str
    domain: str
    url: str
    position: int
    serp_features: dict[str, bool] = field(default_factory=dict)
    fetched_at: str = field(default_factory=_now_utc)
    source: str = "unknown"
    raw_payload_hash: str | None = None  # SHA-256 of provider response for audit


@dataclass
class BacklinkResult:
    """SEO authority metrics for a domain."""

    domain: str
    domain_rating: int | None = None       # Ahrefs-style DR (DataForSEO)
    domain_authority: int | None = None    # Moz DA
    page_authority: int | None = None      # Moz PA
    spam_score: int | None = None          # Moz Spam Score
    referring_domains_count: int | None = None
    backlinks_count: int | None = None
    organic_traffic_estimate: int | None = None
    organic_keywords_count: int | None = None
    source: str = "unknown"
    as_of: str = field(default_factory=_now_utc)


@dataclass
class TechResult:
    """Technology fingerprint for a domain."""

    domain: str
    platform: str | None = None
    platform_confidence: float = 0.0
    technologies: list[str] = field(default_factory=list)
    technology_count: int = 0
    detected_via: str = "unknown"
    as_of: str = field(default_factory=_now_utc)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class DataSource(abc.ABC):
    """
    Abstract interface for any pluggable data provider.

    Concrete implementations live alongside this file:
      - DataForSEOSource   (dataforseo.py)  — preferred production provider
      - MockSource         (mock.py)        — deterministic fixture data for tests

    Agents call only these methods. Never call a provider SDK directly in
    agent code — always go through a DataSource instance.
    """

    source_id: str  # Must match a value in VARIABLES["DATA_SOURCE"]

    # ------------------------------------------------------------------
    # SERP methods — used by Agent 2 (SERP Discovery)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def submit_serp_tasks(
        self,
        keywords: list[str],
        geo: str = "2826",          # DataForSEO location code for United Kingdom
        language: str = "en",
        device: str = "desktop",
    ) -> list[str]:
        """
        Submit a batch of SERP queries to the provider.

        Returns a list of task/job IDs that can be polled with
        get_serp_results(). For providers without async queuing, return
        immediately with synthetic IDs and store results internally.
        """
        ...

    @abc.abstractmethod
    async def get_serp_results(
        self, task_ids: list[str]
    ) -> list[SerpResult]:
        """
        Retrieve completed SERP results for the given task IDs.

        Raises ProviderNotReady if tasks are still processing.
        Implementations must handle exponential backoff internally.
        """
        ...

    # ------------------------------------------------------------------
    # SEO / backlink methods — used by Agent 4 (SEO Metrics)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def get_backlink_metrics(
        self, domains: list[str]
    ) -> list[BacklinkResult]:
        """Fetch domain authority, backlinks, and traffic estimates."""
        ...

    # ------------------------------------------------------------------
    # Technology detection — used by Agent 5 (Tech Stack)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def get_tech_stack(
        self, domain: str
    ) -> TechResult:
        """
        Fingerprint the technology stack of a domain.

        Implementations may use Wappalyzer via Playwright, HTTP header
        analysis, or any other method.
        """
        ...

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def provider_meta(self) -> dict[str, Any]:
        """Return provider metadata for logging / audit records."""
        return {"source_id": self.source_id}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderNotReady(Exception):
    """SERP tasks submitted but results not yet available — retry later."""


class ProviderRateLimited(Exception):
    """Provider returned HTTP 429. Caller should apply exponential backoff."""


class ProviderError(Exception):
    """Unrecoverable provider error. Job should be sent to dead letter queue."""
