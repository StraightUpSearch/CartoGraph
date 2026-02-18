"""
Tier gating — feature flags, field masking, and quota enforcement

This module is the single source of truth for what each subscription tier can
access. All enforcement goes through this module; agents and route handlers
never contain hard-coded tier logic.

Usage:
    from app.tier_gating import TierGate, mask_domain_by_tier

    gate = TierGate(tier="starter")
    gate.check_lookup_quota(workspace)            # raises HTTPException if exceeded
    gate.check_row_limit(requested=5000)          # raises HTTPException if over limit
    masked = mask_domain_by_tier(domain_dict, tier="starter")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

# ---------------------------------------------------------------------------
# Tier limit definitions — all numeric limits per billing cycle
# ---------------------------------------------------------------------------

@dataclass
class TierLimits:
    tier: str
    max_lookups_per_month: int | None    # None = unlimited
    max_rows_per_view: int | None
    max_export_credits_per_month: int | None
    max_api_calls_per_month: int | None
    max_saved_lists: int | None
    max_alerts: int | None
    max_team_seats: int
    api_rate_limit_per_min: int | None    # None = no limit
    historical_months: int | None         # None = no history
    # Field group access
    allowed_field_groups: list[str] = field(default_factory=list)
    all_fields: bool = False
    # Feature flags
    can_export_csv: bool = False
    can_use_api: bool = False
    can_use_webhooks: bool = False
    can_white_label: bool = False
    can_share_workspace: bool = False
    daily_trending: bool = False


TIER_LIMITS: dict[str, TierLimits] = {
    "free": TierLimits(
        tier="free",
        max_lookups_per_month=25,
        max_rows_per_view=100,
        max_export_credits_per_month=0,
        max_api_calls_per_month=0,
        max_saved_lists=1,
        max_alerts=0,
        max_team_seats=1,
        api_rate_limit_per_min=None,
        historical_months=None,
        allowed_field_groups=["discovery_basic", "ecommerce_basic", "seo_basic", "meta_basic"],
        all_fields=False,
        can_export_csv=False,
        can_use_api=False,
        can_use_webhooks=False,
    ),
    "starter": TierLimits(
        tier="starter",
        max_lookups_per_month=500,
        max_rows_per_view=5000,
        max_export_credits_per_month=50,
        max_api_calls_per_month=0,
        max_saved_lists=5,
        max_alerts=5,
        max_team_seats=1,
        api_rate_limit_per_min=None,
        historical_months=None,
        allowed_field_groups=[
            "discovery_basic", "ecommerce_basic", "seo_basic", "meta_basic",
            "ecommerce", "seo_metrics", "technical_layer", "contact_social",
        ],
        all_fields=False,
        can_export_csv=True,
        can_use_api=False,
        can_use_webhooks=False,
    ),
    "professional": TierLimits(
        tier="professional",
        max_lookups_per_month=None,
        max_rows_per_view=50_000,
        max_export_credits_per_month=500,
        max_api_calls_per_month=10_000,
        max_saved_lists=25,
        max_alerts=50,
        max_team_seats=3,
        api_rate_limit_per_min=100,
        historical_months=3,
        allowed_field_groups=[],
        all_fields=True,
        can_export_csv=True,
        can_use_api=True,
        can_use_webhooks=True,
        daily_trending=True,
    ),
    "business": TierLimits(
        tier="business",
        max_lookups_per_month=None,
        max_rows_per_view=250_000,
        max_export_credits_per_month=2_000,
        max_api_calls_per_month=50_000,
        max_saved_lists=None,
        max_alerts=None,
        max_team_seats=10,
        api_rate_limit_per_min=500,
        historical_months=12,
        allowed_field_groups=[],
        all_fields=True,
        can_export_csv=True,
        can_use_api=True,
        can_use_webhooks=True,
        can_white_label=True,
        can_share_workspace=True,
        daily_trending=True,
    ),
    "enterprise": TierLimits(
        tier="enterprise",
        max_lookups_per_month=None,
        max_rows_per_view=None,
        max_export_credits_per_month=None,
        max_api_calls_per_month=None,
        max_saved_lists=None,
        max_alerts=None,
        max_team_seats=999,
        api_rate_limit_per_min=None,
        historical_months=None,  # unlimited
        allowed_field_groups=[],
        all_fields=True,
        can_export_csv=True,
        can_use_api=True,
        can_use_webhooks=True,
        can_white_label=True,
        can_share_workspace=True,
        daily_trending=True,
    ),
}

# ---------------------------------------------------------------------------
# JSONB field groups — which fields are returned at each tier
# ---------------------------------------------------------------------------

# Fields always included regardless of tier
_ALWAYS_VISIBLE: set[str] = {"domain_id", "domain", "country", "tld", "status",
                              "first_seen_at", "last_updated_at", "schema_version"}

# Sub-keys within each JSONB group gated per tier
_FIELD_GATING: dict[str, dict[str, list[str] | None]] = {
    # None = all sub-keys allowed
    "discovery": {
        "free":         ["method", "first_seen", "last_verified"],
        "starter":      ["method", "first_seen", "last_verified", "intent_type"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "ecommerce": {
        "free":         ["platform"],
        "starter":      ["platform", "platform_confidence", "product_count_estimate",
                         "category_primary", "currency"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "seo_metrics": {
        "free":         ["domain_rating"],
        "starter":      ["domain_rating", "domain_authority", "organic_traffic_estimate",
                         "referring_domains_count", "organic_traffic_trend"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "intent_layer": {
        "free":         None,    # fully gated at free — field not returned
        "starter":      ["commercial_intent_score"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "serp_intelligence": {
        "free":         None,
        "starter":      ["serp_features"],  # feature flags only, no top queries
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "technical_layer": {
        "free":         None,
        "starter":      ["tech_stack"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "contact": {
        "free":         None,
        "starter":      ["social_profiles", "has_contact_form"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "meta": {
        "free":         ["ssl_valid", "mobile_friendly", "page_speed_score"],
        "starter":      ["ssl_valid", "mobile_friendly", "page_speed_score", "language", "title"],
        "professional": None,
        "business":     None,
        "enterprise":   None,
    },
    "change_tracking": {
        "free":         None,
        "starter":      None,
        "professional": ["mom_traffic_delta", "trending_score"],
        "business":     None,
        "enterprise":   None,
    },
    "marketplace_overlap":  {"free": None, "starter": None, "professional": None, "business": None, "enterprise": None},
    "paid_ads_presence":    {"free": None, "starter": None, "professional": None, "business": None, "enterprise": None},
    "confidence_score":     {"free": ["value"], "starter": None, "professional": None, "business": None, "enterprise": None},
    "pipeline":             {"free": None, "starter": None, "professional": None, "business": None, "enterprise": None},
    "ai_summary":           {"free": None, "starter": None, "professional": None, "business": None, "enterprise": None},
}

# Groups completely hidden below a tier (None in _FIELD_GATING at free means hidden)
_HIDDEN_FOR_FREE: set[str] = {
    "intent_layer", "serp_intelligence", "technical_layer", "contact",
    "change_tracking", "marketplace_overlap", "paid_ads_presence",
    "pipeline", "ai_summary",
}
_HIDDEN_FOR_STARTER: set[str] = {"change_tracking"}


# ---------------------------------------------------------------------------
# Field masking
# ---------------------------------------------------------------------------


def _filter_jsonb(blob: dict[str, Any] | None, allowed_keys: list[str] | None) -> dict[str, Any] | None:
    """Return only allowed sub-keys from a JSONB blob. None allowed_keys = return everything."""
    if blob is None:
        return None
    if allowed_keys is None:
        return blob
    return {k: v for k, v in blob.items() if k in allowed_keys}


def mask_domain_by_tier(domain_data: dict[str, Any], tier: str) -> dict[str, Any]:
    """
    Apply field masking to a full domain record based on subscription tier.

    Returns a new dict — never mutates the input.
    Fields not accessible at the given tier are replaced with None and a
    `_gated` flag so the frontend can show blur/upgrade prompts.
    """
    tier_lower = tier.lower()
    if tier_lower not in TIER_LIMITS:
        tier_lower = "free"  # default to most restrictive

    result: dict[str, Any] = {}

    # Always pass through scalar fields
    for key in _ALWAYS_VISIBLE:
        result[key] = domain_data.get(key)

    # Apply per-group gating
    for group, tier_map in _FIELD_GATING.items():
        allowed_keys: list[str] | None = tier_map.get(tier_lower)
        blob: dict[str, Any] | None = domain_data.get(group)

        # Check if this group is completely hidden at this tier
        if tier_lower == "free" and group in _HIDDEN_FOR_FREE:
            result[group] = None
            result[f"{group}_gated"] = True
            continue
        if tier_lower == "starter" and group in _HIDDEN_FOR_STARTER:
            result[group] = None
            result[f"{group}_gated"] = True
            continue

        if allowed_keys is None:
            # Full access to this group
            result[group] = blob
        else:
            # Partial access — filter to allowed sub-keys
            result[group] = _filter_jsonb(blob, allowed_keys)
            if blob and set(blob.keys()) - set(allowed_keys):
                result[f"{group}_gated"] = True  # tell frontend some keys are hidden

    return result


# ---------------------------------------------------------------------------
# Quota enforcement helpers
# ---------------------------------------------------------------------------


class TierGate:
    """Stateless helper for enforcing tier quotas in route handlers."""

    def __init__(self, tier: str) -> None:
        self.tier = tier.lower()
        self.limits = TIER_LIMITS.get(self.tier, TIER_LIMITS["free"])

    def require_feature(self, feature: str) -> None:
        """
        Raise 403 if the given feature flag is False for this tier.
        feature: 'can_export_csv' | 'can_use_api' | 'can_use_webhooks' | 'can_white_label'
        """
        if not getattr(self.limits, feature, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "feature_gated",
                    "feature": feature,
                    "current_tier": self.tier,
                    "message": f"This feature is not available on the {self.tier} plan.",
                },
            )

    def check_row_limit(self, requested: int) -> None:
        """Raise 403 if requested rows exceed the tier's per-view limit."""
        limit = self.limits.max_rows_per_view
        if limit is not None and requested > limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "row_limit_exceeded",
                    "limit": limit,
                    "requested": requested,
                    "current_tier": self.tier,
                },
            )

    def check_lookup_quota(self, used: int) -> None:
        """Raise 429 if monthly domain lookups are exhausted."""
        limit = self.limits.max_lookups_per_month
        if limit is not None and used >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "lookup_quota_exceeded",
                    "limit": limit,
                    "used": used,
                    "current_tier": self.tier,
                    "upgrade_message": f"You've used all {limit} lookups this month. "
                                       "Upgrade your plan for more.",
                },
            )

    def check_export_credits(self, used: int, requested: int = 1) -> None:
        """Raise 429 if export credits are exhausted."""
        self.require_feature("can_export_csv")
        limit = self.limits.max_export_credits_per_month
        if limit is not None and (used + requested) > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "export_credits_exhausted",
                    "limit": limit,
                    "used": used,
                    "current_tier": self.tier,
                },
            )

    def check_alert_limit(self, current_count: int) -> None:
        """Raise 403 if alert count is at the tier limit."""
        limit = self.limits.max_alerts
        if limit is not None and current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "alert_limit_reached",
                    "limit": limit,
                    "current_tier": self.tier,
                },
            )

    def clamp_page_size(self, requested: int, default: int = 50) -> int:
        """Return the smaller of requested page_size and the tier row limit."""
        limit = self.limits.max_rows_per_view
        effective = requested if requested > 0 else default
        if limit is not None:
            return min(effective, limit)
        return effective
