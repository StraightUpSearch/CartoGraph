"""Tests for Agent 4: SEO Metrics Enrichment"""

import asyncio
import json

import pytest

from app.agents.agent4_seo_metrics import (
    SeoMetricsOutput,
    _merge_backlink_results,
    enrich_domain_seo,
)
from app.agents.sources.base import BacklinkResult
from app.agents.sources.mock import MockSource


def _dfs_result(domain: str = "example.co.uk", **kwargs: object) -> BacklinkResult:
    return BacklinkResult(
        domain=domain,
        domain_rating=kwargs.get("domain_rating", 54),  # type: ignore[arg-type]
        referring_domains_count=kwargs.get("referring_domains_count", 1840),  # type: ignore[arg-type]
        backlinks_count=kwargs.get("backlinks_count", 23400),  # type: ignore[arg-type]
        organic_traffic_estimate=kwargs.get("organic_traffic_estimate", 89000),  # type: ignore[arg-type]
        source="dataforseo_backlinks",
    )


def _moz_result(domain: str = "example.co.uk", **kwargs: object) -> BacklinkResult:
    return BacklinkResult(
        domain=domain,
        domain_authority=kwargs.get("domain_authority", 48),  # type: ignore[arg-type]
        page_authority=kwargs.get("page_authority", 45),  # type: ignore[arg-type]
        spam_score=kwargs.get("spam_score", 12),  # type: ignore[arg-type]
        source="moz_api",
    )


# ---------------------------------------------------------------------------
# Unit tests: _merge_backlink_results
# ---------------------------------------------------------------------------

def test_merge_combines_dfs_and_moz() -> None:
    result = _merge_backlink_results(_dfs_result(), _moz_result())
    assert result.domain_rating == 54
    assert result.domain_authority == 48
    assert result.spam_score == 12
    assert "dataforseo_backlinks" in result.sources_used
    assert "moz_api" in result.sources_used


def test_merge_works_with_only_dfs() -> None:
    result = _merge_backlink_results(_dfs_result(), None)
    assert result.domain_rating == 54
    assert result.domain_authority is None


def test_merge_works_with_only_moz() -> None:
    result = _merge_backlink_results(None, _moz_result())
    assert result.domain_authority == 48
    assert result.domain_rating is None


def test_authority_divergence_flagged_when_over_30() -> None:
    dfs = _dfs_result(domain_rating=80)
    moz = _moz_result(domain_authority=40)
    result = _merge_backlink_results(dfs, moz)
    assert result.authority_divergence_flagged is True


def test_authority_divergence_not_flagged_within_30() -> None:
    dfs = _dfs_result(domain_rating=55)
    moz = _moz_result(domain_authority=45)
    result = _merge_backlink_results(dfs, moz)
    assert result.authority_divergence_flagged is False


def test_low_traffic_flagged() -> None:
    dfs = _dfs_result(organic_traffic_estimate=5)
    result = _merge_backlink_results(dfs, None)
    assert result.low_traffic_flagged is True


def test_high_spam_flagged() -> None:
    dfs = _dfs_result()
    moz = _moz_result(spam_score=75)
    result = _merge_backlink_results(dfs, moz)
    assert result.high_spam_flagged is True


# ---------------------------------------------------------------------------
# Integration test using MockSource
# ---------------------------------------------------------------------------

def test_enrich_domain_seo_with_mock_source() -> None:
    result = asyncio.get_event_loop().run_until_complete(
        enrich_domain_seo(
            domain="example.co.uk",
            primary_source=MockSource(),
            supplementary_source=MockSource(),
            job_id="test-004",
        )
    )
    assert isinstance(result, SeoMetricsOutput)
    assert result.agent == "agent4_seo_metrics"
    assert result.job_id == "test-004"
    assert result.domain == "example.co.uk"
    assert result.schema_version == "1.0.0"


def test_output_is_json_serialisable() -> None:
    result = asyncio.get_event_loop().run_until_complete(
        enrich_domain_seo(
            domain="example.co.uk",
            primary_source=MockSource(),
            supplementary_source=MockSource(),
        )
    )
    json.dumps(result.model_dump())
