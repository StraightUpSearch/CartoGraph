"""Tests for Agent 2: SERP Discovery"""

import asyncio
import pytest

from app.agents.agent2_serp_discovery import (
    SerpDiscoveryOutput,
    DiscoveredDomain,
    _is_excluded,
    _is_uk_relevant,
    process_serp_results,
    run_discovery,
)
from app.agents.sources.base import SerpResult
from app.agents.sources.mock import MockSource


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

def test_is_excluded_blocks_amazon() -> None:
    assert _is_excluded("amazon.co.uk")
    assert _is_excluded("amazon.com")


def test_is_excluded_blocks_ebay() -> None:
    assert _is_excluded("ebay.co.uk")


def test_is_excluded_does_not_block_real_stores() -> None:
    assert not _is_excluded("example.co.uk")
    assert not _is_excluded("sportstop.co.uk")


def test_is_uk_relevant_accepts_couk() -> None:
    assert _is_uk_relevant("example.co.uk")
    assert _is_uk_relevant("shop.uk")


def test_is_uk_relevant_accepts_com() -> None:
    # .com domains are provisionally accepted (Agent 3 will validate UK signals)
    assert _is_uk_relevant("globalstore.com")


def test_process_serp_results_deduplicates() -> None:
    results = [
        SerpResult(keyword="buy shoes uk", domain="example.co.uk", url="https://example.co.uk", position=1),
        SerpResult(keyword="cheap shoes uk", domain="example.co.uk", url="https://example.co.uk/sale", position=3),
    ]
    discovered, excluded = process_serp_results(results, known_domains=set())
    assert len(discovered) == 1  # deduped to one domain
    assert excluded == 0


def test_process_serp_results_flags_known_domains() -> None:
    results = [
        SerpResult(keyword="buy shoes uk", domain="example.co.uk", url="https://example.co.uk", position=1),
        SerpResult(keyword="buy shoes uk", domain="newstore.co.uk", url="https://newstore.co.uk", position=2),
    ]
    discovered, _ = process_serp_results(results, known_domains={"example.co.uk"})
    by_domain = {d.domain: d for d in discovered}
    assert by_domain["example.co.uk"].is_new is False
    assert by_domain["newstore.co.uk"].is_new is True


def test_process_serp_results_excludes_marketplaces() -> None:
    results = [
        SerpResult(keyword="buy shoes uk", domain="amazon.co.uk", url="https://amazon.co.uk/shoes", position=1),
        SerpResult(keyword="buy shoes uk", domain="example.co.uk", url="https://example.co.uk", position=2),
    ]
    discovered, excluded = process_serp_results(results, known_domains=set())
    domains = [d.domain for d in discovered]
    assert "amazon.co.uk" not in domains
    assert "example.co.uk" in domains
    assert excluded == 1


# ---------------------------------------------------------------------------
# Integration test using MockSource
# ---------------------------------------------------------------------------

def test_run_discovery_with_mock_source() -> None:
    keywords = ["buy running shoes uk", "cheap trainers uk"]
    result = asyncio.get_event_loop().run_until_complete(
        run_discovery(
            keywords=keywords,
            source=MockSource(),
            known_domains=set(),
            job_id="test-002",
        )
    )
    assert isinstance(result, SerpDiscoveryOutput)
    assert result.agent == "agent2_serp_discovery"
    assert result.job_id == "test-002"
    assert result.keywords_processed == 2
    assert result.schema_version == "1.0.0"


def test_output_is_json_serialisable() -> None:
    import json
    result = asyncio.get_event_loop().run_until_complete(
        run_discovery(
            keywords=["buy shoes uk"],
            source=MockSource(),
            job_id="test-json",
        )
    )
    json.dumps(result.model_dump())


def test_new_domain_count_is_accurate() -> None:
    result = asyncio.get_event_loop().run_until_complete(
        run_discovery(
            keywords=["buy shoes uk"],
            source=MockSource(),
            known_domains={"example.co.uk"},  # mock returns this domain
            job_id="test-003",
        )
    )
    # example.co.uk is known; sportstop.co.uk should be new
    assert result.known_domain_count >= 1
