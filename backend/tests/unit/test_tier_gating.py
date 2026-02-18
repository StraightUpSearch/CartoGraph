"""
Unit tests for tier gating logic (no database required).

Covers:
  - mask_domain_by_tier: field inclusion/exclusion per tier
  - TierGate.check_lookup_quota: raises 429 when limit hit
  - TierGate.check_export_credits: raises 429 when credits exhausted
  - TierGate.require_feature: raises 403 when feature not in tier
  - TierGate.check_alert_limit: raises 403 when limit hit
  - TierGate.clamp_page_size: respects tier row limit
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.tier_gating import TIER_LIMITS, TierGate, mask_domain_by_tier


# ---------------------------------------------------------------------------
# Fixture: minimal domain dict
# ---------------------------------------------------------------------------

_FULL_DOMAIN: dict = {
    "domain_id": "00000000-0000-0000-0000-000000000001",
    "domain": "example.co.uk",
    "country": "UK",
    "tld": ".co.uk",
    "status": "active",
    "first_seen_at": "2024-01-01T00:00:00",
    "last_updated_at": "2024-06-01T00:00:00",
    "schema_version": "1.0.0",
    "discovery": {"method": "serp", "first_seen": "2024-01-01", "intent_type": "commercial"},
    "ecommerce": {"platform": "Shopify", "category_primary": "Fashion", "checkout_url": "/checkout"},
    "seo_metrics": {"domain_rating": 55, "domain_authority": 48, "organic_traffic_estimate": 90000},
    "intent_layer": {"commercial_intent_score": 8, "modifier_density": 0.7},
    "serp_intelligence": {"serp_features": {"shopping_carousel": True}, "top_queries": ["shoes uk"]},
    "technical_layer": {"tech_stack": ["Shopify"], "checkout_path_detected": True},
    "contact": {"social_profiles": {"twitter": "@example"}, "has_contact_form": True, "email": "info@example.co.uk"},
    "marketplace_overlap": {"amazon": True},
    "paid_ads_presence": {"google_shopping": True},
    "meta": {"ssl_valid": True, "mobile_friendly": True, "page_speed_score": 82, "language": "en", "title": "Example"},
    "change_tracking": {"mom_traffic_delta": 12.5, "trending_score": 6.2},
    "confidence_score": {"value": 0.91, "evidence": ["Shopify detected"]},
    "pipeline": {"last_run": "2024-06-01"},
    "ai_summary": {"summary": "High-intent fashion ecommerce."},
}


# ---------------------------------------------------------------------------
# mask_domain_by_tier: always-visible fields
# ---------------------------------------------------------------------------


def test_always_visible_fields_in_all_tiers() -> None:
    for tier in TIER_LIMITS:
        masked = mask_domain_by_tier(_FULL_DOMAIN, tier)
        assert masked["domain"] == "example.co.uk"
        assert masked["country"] == "UK"
        assert masked["status"] == "active"


# ---------------------------------------------------------------------------
# mask_domain_by_tier: free tier restrictions
# ---------------------------------------------------------------------------


def test_free_tier_hides_intent_layer() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    assert masked.get("intent_layer") is None
    assert masked.get("intent_layer_gated") is True


def test_free_tier_hides_serp_intelligence() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    assert masked.get("serp_intelligence") is None
    assert masked.get("serp_intelligence_gated") is True


def test_free_tier_hides_technical_layer() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    assert masked.get("technical_layer") is None


def test_free_tier_hides_contact() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    assert masked.get("contact") is None


def test_free_tier_allows_platform_in_ecommerce() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    ecom = masked.get("ecommerce")
    assert ecom is not None
    assert ecom.get("platform") == "Shopify"
    # checkout_url should be gated
    assert "checkout_url" not in (ecom or {})


def test_free_tier_exposes_domain_rating_in_seo() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    seo = masked.get("seo_metrics")
    assert seo is not None
    assert seo.get("domain_rating") == 55
    # domain_authority should NOT be present at free tier
    assert "domain_authority" not in seo


def test_free_tier_confidence_value_only() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "free")
    conf = masked.get("confidence_score")
    assert conf is not None
    assert conf.get("value") == pytest.approx(0.91)
    assert "evidence" not in conf


# ---------------------------------------------------------------------------
# mask_domain_by_tier: starter tier
# ---------------------------------------------------------------------------


def test_starter_tier_exposes_intent_score() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "starter")
    intent = masked.get("intent_layer")
    assert intent is not None
    assert intent.get("commercial_intent_score") == 8


def test_starter_tier_hides_change_tracking() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "starter")
    assert masked.get("change_tracking") is None
    assert masked.get("change_tracking_gated") is True


def test_starter_tier_exposes_serp_features() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "starter")
    serp = masked.get("serp_intelligence")
    assert serp is not None
    assert "serp_features" in serp
    # top_queries should be gated at starter
    assert "top_queries" not in serp


# ---------------------------------------------------------------------------
# mask_domain_by_tier: professional / enterprise get all fields
# ---------------------------------------------------------------------------


def test_professional_tier_full_seo_access() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "professional")
    seo = masked.get("seo_metrics")
    assert seo is not None
    assert seo.get("domain_rating") == 55
    assert seo.get("domain_authority") == 48
    assert seo.get("organic_traffic_estimate") == 90000


def test_enterprise_tier_gets_all_jsonb_groups() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "enterprise")
    for group in [
        "discovery", "ecommerce", "seo_metrics", "intent_layer",
        "serp_intelligence", "technical_layer", "contact", "change_tracking",
    ]:
        assert masked.get(group) is not None, f"{group} should be visible at enterprise tier"


def test_unknown_tier_defaults_to_free() -> None:
    masked = mask_domain_by_tier(_FULL_DOMAIN, "unicorn_tier")
    assert masked.get("intent_layer") is None  # same as free


# ---------------------------------------------------------------------------
# TierGate: check_lookup_quota
# ---------------------------------------------------------------------------


def test_lookup_quota_passes_under_limit() -> None:
    gate = TierGate("free")
    # Free tier has 25 lookups/month — 24 used is fine
    gate.check_lookup_quota(24)  # should not raise


def test_lookup_quota_raises_at_limit() -> None:
    gate = TierGate("free")
    with pytest.raises(HTTPException) as exc_info:
        gate.check_lookup_quota(25)  # 25 used = limit reached
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "lookup_quota_exceeded"


def test_lookup_quota_unlimited_for_professional() -> None:
    gate = TierGate("professional")
    gate.check_lookup_quota(999_999)  # should not raise — unlimited


# ---------------------------------------------------------------------------
# TierGate: require_feature
# ---------------------------------------------------------------------------


def test_require_feature_raises_for_free_webhooks() -> None:
    gate = TierGate("free")
    with pytest.raises(HTTPException) as exc_info:
        gate.require_feature("can_use_webhooks")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "feature_gated"


def test_require_feature_passes_for_professional_webhooks() -> None:
    gate = TierGate("professional")
    gate.require_feature("can_use_webhooks")  # should not raise


def test_require_feature_raises_csv_for_free() -> None:
    gate = TierGate("free")
    with pytest.raises(HTTPException) as exc_info:
        gate.require_feature("can_export_csv")
    assert exc_info.value.status_code == 403


def test_require_feature_passes_csv_for_starter() -> None:
    gate = TierGate("starter")
    gate.require_feature("can_export_csv")  # should not raise


# ---------------------------------------------------------------------------
# TierGate: check_export_credits
# ---------------------------------------------------------------------------


def test_export_credits_raises_for_free() -> None:
    gate = TierGate("free")
    with pytest.raises(HTTPException) as exc_info:
        gate.check_export_credits(used=0, requested=1)
    # Free tier cannot export — require_feature raises first
    assert exc_info.value.status_code == 403


def test_export_credits_exhausted_for_starter() -> None:
    gate = TierGate("starter")
    with pytest.raises(HTTPException) as exc_info:
        gate.check_export_credits(used=50, requested=1)  # starter limit is 50
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "export_credits_exhausted"


def test_export_credits_ok_for_starter_under_limit() -> None:
    gate = TierGate("starter")
    gate.check_export_credits(used=49, requested=1)  # should not raise


def test_export_credits_unlimited_for_enterprise() -> None:
    gate = TierGate("enterprise")
    gate.check_export_credits(used=999_999, requested=1)  # should not raise


# ---------------------------------------------------------------------------
# TierGate: check_alert_limit
# ---------------------------------------------------------------------------


def test_alert_limit_raises_for_free() -> None:
    gate = TierGate("free")
    with pytest.raises(HTTPException) as exc_info:
        gate.check_alert_limit(current_count=0)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "alert_limit_reached"


def test_alert_limit_passes_for_starter_under_limit() -> None:
    gate = TierGate("starter")
    gate.check_alert_limit(current_count=4)  # starter allows 5 — should not raise


def test_alert_limit_raises_for_starter_at_limit() -> None:
    gate = TierGate("starter")
    with pytest.raises(HTTPException):
        gate.check_alert_limit(current_count=5)


def test_alert_limit_unlimited_for_enterprise() -> None:
    gate = TierGate("enterprise")
    gate.check_alert_limit(current_count=999_999)  # should not raise


# ---------------------------------------------------------------------------
# TierGate: clamp_page_size
# ---------------------------------------------------------------------------


def test_clamp_page_size_free_limits_to_100() -> None:
    gate = TierGate("free")
    assert gate.clamp_page_size(500) == 100


def test_clamp_page_size_uses_default_when_zero() -> None:
    gate = TierGate("starter")
    # Default is 50 when requested is 0; clamped to min(50, 5000) = 50
    assert gate.clamp_page_size(0, default=50) == 50


def test_clamp_page_size_enterprise_returns_requested() -> None:
    gate = TierGate("enterprise")
    assert gate.clamp_page_size(50_000) == 50_000
