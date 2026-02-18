"""
MockSource — deterministic fixture-based DataSource for tests

Returns realistic but hardcoded responses so agent tests do not need
live API credentials or network access.
"""

from __future__ import annotations

from app.agents.sources.base import (
    BacklinkResult,
    DataSource,
    SerpResult,
    TechResult,
)

_MOCK_SERP_RESULTS = [
    SerpResult(
        keyword="buy running shoes uk",
        domain="example.co.uk",
        url="https://example.co.uk/running-shoes",
        position=1,
        serp_features={
            "shopping_carousel": True,
            "people_also_ask": True,
            "featured_snippet": False,
            "local_pack": False,
            "sitelinks": True,
            "image_pack": False,
            "ai_overview": False,
        },
        source="mock",
    ),
    SerpResult(
        keyword="buy running shoes uk",
        domain="sportstop.co.uk",
        url="https://sportstop.co.uk/footwear/running",
        position=2,
        serp_features={
            "shopping_carousel": True,
            "people_also_ask": True,
            "featured_snippet": False,
            "local_pack": False,
            "sitelinks": False,
            "image_pack": False,
            "ai_overview": False,
        },
        source="mock",
    ),
]

_MOCK_BACKLINK_RESULTS = [
    BacklinkResult(
        domain="example.co.uk",
        domain_rating=54,
        domain_authority=48,
        spam_score=12,
        referring_domains_count=1840,
        backlinks_count=23400,
        organic_traffic_estimate=89000,
        organic_keywords_count=14200,
        source="mock",
    ),
]

_MOCK_TECH_RESULTS = {
    "example.co.uk": TechResult(
        domain="example.co.uk",
        platform="Shopify",
        platform_confidence=0.95,
        technologies=["Shopify", "Klaviyo", "Stripe", "Cloudflare", "GA4"],
        technology_count=5,
        detected_via="mock",
    ),
}


class MockSource(DataSource):
    """Fixture-based provider — no network calls, deterministic output."""

    source_id = "mock"

    async def submit_serp_tasks(
        self,
        keywords: list[str],
        geo: str = "2826",
        language: str = "en",
        device: str = "desktop",
    ) -> list[str]:
        # Return a synthetic task ID per keyword
        return [f"mock-task-{i}" for i in range(len(keywords))]

    async def get_serp_results(self, task_ids: list[str]) -> list[SerpResult]:
        # Return mock results regardless of task IDs
        return _MOCK_SERP_RESULTS

    async def get_backlink_metrics(
        self, domains: list[str]
    ) -> list[BacklinkResult]:
        return [r for r in _MOCK_BACKLINK_RESULTS if r.domain in domains]

    async def get_tech_stack(self, domain: str) -> TechResult:
        return _MOCK_TECH_RESULTS.get(
            domain,
            TechResult(domain=domain, detected_via="mock"),
        )
