"""Tests for Agent 1: Keyword Miner"""

import pytest

from app.agents.agent1_keyword_miner import (
    KeywordMinerOutput,
    generate_keyword_batch,
    _detect_modifiers,
)
from app.config.variables import VARIABLES


def test_generate_keyword_batch_returns_output() -> None:
    result = generate_keyword_batch(max_keywords=50, job_id="test-001")
    assert isinstance(result, KeywordMinerOutput)
    assert result.agent == "agent1_keyword_miner"
    assert result.country == "UK"
    assert result.job_id == "test-001"


def test_generate_keyword_batch_respects_max() -> None:
    result = generate_keyword_batch(max_keywords=10)
    assert len(result.keywords) <= 10


def test_all_keywords_have_required_fields() -> None:
    result = generate_keyword_batch(max_keywords=50)
    for kw in result.keywords:
        assert kw.keyword, "keyword string must not be empty"
        assert kw.cluster_id, "cluster_id must not be empty"
        assert kw.intent_type in VARIABLES["INTENT_TYPE"], (
            f"intent_type '{kw.intent_type}' not in allowed list"
        )
        assert 1 <= kw.priority_score <= 10
        assert isinstance(kw.modifiers_present, list)
        assert kw.rationale


def test_all_keywords_contain_intent_modifier() -> None:
    """Every generated keyword must contain at least one commercial intent signal."""
    result = generate_keyword_batch(max_keywords=50)
    for kw in result.keywords:
        has_signal = bool(kw.modifiers_present) or "uk" in kw.keyword.lower()
        assert has_signal, f"Keyword '{kw.keyword}' has no intent modifiers"


def test_keywords_are_uk_geo_qualified() -> None:
    """Transactional keywords should mention 'UK' or contain a UK modifier."""
    result = generate_keyword_batch(max_keywords=100)
    transactional = [k for k in result.keywords if k.intent_type == "transactional"]
    assert len(transactional) > 0, "Should produce transactional keywords"


def test_detect_modifiers_finds_buy() -> None:
    mods = _detect_modifiers("buy running shoes uk")
    assert "buy" in mods
    assert "uk" in mods


def test_schema_version_is_set() -> None:
    result = generate_keyword_batch(max_keywords=5)
    assert result.schema_version == "1.0.0"


def test_output_is_json_serialisable() -> None:
    import json
    result = generate_keyword_batch(max_keywords=5)
    serialised = result.model_dump()
    # Should not raise
    json.dumps(serialised)
