"""Tests for Agent 6: Intent Scoring"""

import json

from app.agents.agent6_intent_scoring import (
    IntentScoringOutput,
    _compute_trending_score,
    _modifier_density,
    _serp_feature_score,
    score_domain,
)
from app.config.variables import SERP_FEATURE_WEIGHTS


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

def test_modifier_density_zero_when_no_keywords() -> None:
    assert _modifier_density({}, []) == 0.0


def test_modifier_density_full_when_all_match() -> None:
    kw = {"total_keywords": 10, "modifier_keyword_count": 10}
    assert _modifier_density(kw, []) == 1.0


def test_modifier_density_partial() -> None:
    kw = {"total_keywords": 10, "modifier_keyword_count": 5}
    assert _modifier_density(kw, []) == 0.5


def test_serp_feature_score_zero_when_no_features() -> None:
    assert _serp_feature_score({}) == 0.0


def test_serp_feature_score_shopping_carousel_is_max() -> None:
    features = {"shopping_carousel": True}
    score = _serp_feature_score(features)
    assert score == SERP_FEATURE_WEIGHTS["shopping_carousel"]


def test_serp_feature_score_accumulates() -> None:
    features = {"shopping_carousel": True, "people_also_ask": True}
    score = _serp_feature_score(features)
    expected = SERP_FEATURE_WEIGHTS["shopping_carousel"] + SERP_FEATURE_WEIGHTS["people_also_ask"]
    assert score == expected


# ---------------------------------------------------------------------------
# Integration: score_domain
# ---------------------------------------------------------------------------

def test_score_domain_baseline_no_signals() -> None:
    result = score_domain("example.co.uk")
    assert isinstance(result, IntentScoringOutput)
    assert 1 <= result.commercial_intent_score <= 10


def test_score_domain_high_score_with_all_signals() -> None:
    result = score_domain(
        "example.co.uk",
        keyword_profile={"total_keywords": 100, "modifier_keyword_count": 80},
        serp_features={"shopping_carousel": True, "people_also_ask": True, "sitelinks": True},
        technical_signals={
            "product_schema_detected": True,
            "checkout_path_detected": True,
            "paid_ads_seen": True,
            "merchant_listing_eligible": True,
        },
    )
    assert result.commercial_intent_score >= 7


def test_score_domain_low_score_with_no_signals() -> None:
    result = score_domain(
        "blog.example.co.uk",
        keyword_profile={"total_keywords": 100, "modifier_keyword_count": 0},
        serp_features={},
        technical_signals={},
    )
    assert result.commercial_intent_score <= 4


def test_score_is_always_in_range() -> None:
    # Extreme inputs should not overflow the 1–10 range
    result = score_domain(
        "extremetest.co.uk",
        keyword_profile={"total_keywords": 1000, "modifier_keyword_count": 1000},
        serp_features={k: True for k in SERP_FEATURE_WEIGHTS},
        technical_signals={
            "product_schema_detected": True,
            "checkout_path_detected": True,
            "paid_ads_seen": True,
            "merchant_listing_eligible": True,
        },
    )
    assert 1 <= result.commercial_intent_score <= 10


def test_evidence_populated_with_signals() -> None:
    result = score_domain(
        "example.co.uk",
        serp_features={"shopping_carousel": True},
        technical_signals={"product_schema_detected": True},
    )
    assert len(result.evidence) > 0


def test_schema_version_is_set() -> None:
    result = score_domain("example.co.uk")
    assert result.schema_version == "1.0.0"


def test_output_is_json_serialisable() -> None:
    result = score_domain(
        "example.co.uk",
        serp_features={"shopping_carousel": True},
    )
    json.dumps(result.model_dump())


def test_agent_field_is_correct() -> None:
    result = score_domain("example.co.uk")
    assert result.agent == "agent6_intent_scoring"
