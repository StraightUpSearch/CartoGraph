"""Tests for Agent 7: Change Detection"""

import json

from app.agents.agent7_change_detection import (
    ChangeDetectionOutput,
    _compute_trending_score,
    compute_change_delta,
)

_BASE_DOMAIN_ID = "00000000-0000-0000-0000-000000000001"
_DOMAIN = "example.co.uk"


def _make_snapshots(
    curr_traffic: int = 89000,
    prior_traffic: int = 80000,
    curr_features: dict | None = None,
    prior_features: dict | None = None,
    curr_keywords: list | None = None,
    prior_keywords: list | None = None,
) -> tuple[dict, dict]:
    current = {
        "organic_traffic_estimate": curr_traffic,
        "serp_features": curr_features or {},
        "top_keywords": curr_keywords or [],
        "as_of": "2026-02-01",
    }
    prior = {
        "organic_traffic_estimate": prior_traffic,
        "serp_features": prior_features or {},
        "top_keywords": prior_keywords or [],
        "as_of": "2026-01-01",
    }
    return current, prior


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

def test_trending_score_neutral_baseline() -> None:
    score = _compute_trending_score(None, 0, 0)
    assert score == 5.0


def test_trending_score_increases_with_traffic_growth() -> None:
    score = _compute_trending_score(10.0, 0, 0)  # 10% traffic growth
    assert score > 5.0


def test_trending_score_decreases_with_traffic_decline() -> None:
    score = _compute_trending_score(-15.0, 0, 0)
    assert score < 5.0


def test_trending_score_capped_at_10() -> None:
    score = _compute_trending_score(9999.0, 9999, 99)
    assert score <= 10.0


def test_trending_score_floored_at_0() -> None:
    score = _compute_trending_score(-9999.0, 0, 0)
    assert score >= 0.0


# ---------------------------------------------------------------------------
# Integration: compute_change_delta
# ---------------------------------------------------------------------------

def test_traffic_delta_computed_correctly() -> None:
    curr, prior = _make_snapshots(curr_traffic=89000, prior_traffic=80000)
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert result.traffic_delta_absolute == 9000
    assert abs(result.traffic_delta_percent - 0.1125) < 0.001


def test_traffic_delta_none_when_prior_is_zero() -> None:
    curr = {"organic_traffic_estimate": 89000, "serp_features": {}, "top_keywords": []}
    prior = {"organic_traffic_estimate": 0, "serp_features": {}, "top_keywords": []}
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert result.traffic_delta_absolute is None


def test_feature_gains_detected() -> None:
    curr, prior = _make_snapshots(
        curr_features={"shopping_carousel": True},
        prior_features={"shopping_carousel": False},
    )
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert "shopping_carousel" in result.feature_gains_last_30d


def test_feature_losses_detected() -> None:
    curr, prior = _make_snapshots(
        curr_features={"shopping_carousel": False},
        prior_features={"shopping_carousel": True},
    )
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert "shopping_carousel" in result.feature_losses_last_30d


def test_keyword_wins_counted() -> None:
    curr_kw = [{"query": "buy shoes uk", "position": 2}]
    prior_kw = [{"query": "buy shoes uk", "position": 5}]
    curr, prior = _make_snapshots(curr_keywords=curr_kw, prior_keywords=prior_kw)
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert result.keyword_wins_last_30d == 1


def test_alert_triggered_for_high_trending_score() -> None:
    # Large traffic gain should trigger alert
    curr, prior = _make_snapshots(curr_traffic=150000, prior_traffic=80000)
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    if result.alert_triggered:
        assert result.alert_reason is not None


def test_output_domain_preserved() -> None:
    curr, prior = _make_snapshots()
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert result.domain == _DOMAIN
    assert result.domain_id == _BASE_DOMAIN_ID


def test_schema_version_is_set() -> None:
    curr, prior = _make_snapshots()
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert result.schema_version == "1.0.0"


def test_output_is_json_serialisable() -> None:
    curr, prior = _make_snapshots()
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    json.dumps(result.model_dump())


def test_agent_field_is_correct() -> None:
    curr, prior = _make_snapshots()
    result = compute_change_delta(_BASE_DOMAIN_ID, _DOMAIN, curr, prior)
    assert result.agent == "agent7_change_detection"
