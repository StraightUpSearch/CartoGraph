"""
Agent 5: Tech Stack Analyser

Detects ecommerce platform, CMS, analytics tools, payment gateways, email
providers, CDNs, and all installed technologies via self-hosted Wappalyzer.

Data source: Self-hosted Wappalyzer (MIT licence) via Playwright headless Chromium.
Schedule:    Bi-weekly for existing domains; immediate for newly discovered ones.
Capacity:    3 worker instances → ~15,000 domains/day.

Pipeline:
  1. Pull batch sorted by freshness_score descending
  2. Launch headless Chromium via Playwright
  3. Run Wappalyzer fingerprint analysis
  4. Filter: confidence >= 0.5 to record
  5. Compare with previous detection → log changelog
  6. Detect platform plan signals (Shopify Plus vs Basic, etc.)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.agents.sources.wappalyzer import WappalyzerSource
from app.celery_app import celery_app
from app.config.variables import cg_settings

log = logging.getLogger(__name__)

# Platform plan detection patterns (applied after platform is confirmed)
_PLATFORM_PLAN_SIGNALS: dict[str, dict[str, str]] = {
    "Shopify": {
        "plus": "shopifycloud.com/checkout",
        "basic": "checkout.shopify.com",
    },
}

# Technology functional categories (simplified; Wappalyzer provides full taxonomy)
_CATEGORY_MAP: dict[str, list[str]] = {
    "ecommerce_platform": ["Shopify", "WooCommerce", "Magento", "BigCommerce", "Squarespace", "Wix", "PrestaShop"],
    "analytics": ["Google Analytics", "GA4", "Hotjar", "Mixpanel", "Segment", "Plausible"],
    "email_provider": ["Klaviyo", "Mailchimp", "Omnisend", "Drip", "ActiveCampaign"],
    "live_chat": ["Zendesk", "Intercom", "LiveChat", "Tidio", "Crisp"],
    "cdn": ["Cloudflare", "Fastly", "Akamai", "CloudFront"],
    "payment_gateway": ["Stripe", "PayPal", "Klarna", "Worldpay", "Checkout.com", "Braintree"],
    "marketing_tools": ["Meta Pixel", "Google Ads", "TikTok Pixel", "Pinterest Tag"],
}


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class TechStackOutput(BaseModel):
    job_id: str
    agent: str = "agent5_tech_stack"
    schema_version: str = cg_settings.SCHEMA_VERSION
    domain: str
    platform: str | None = None
    platform_plan: str | None = None
    platform_confidence: float = 0.0
    technologies: list[str] = Field(default_factory=list)
    technology_count: int = 0
    categorised: dict[str, list[str]] = Field(default_factory=dict)
    detected_via: str = "wappalyzer_self_hosted"
    # Quality flags
    zero_tech_flagged: bool = False      # No tech detected → manual review
    no_ecom_platform_flagged: bool = False  # No ecom platform → re-classify
    as_of: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------


def _categorise(technologies: list[str]) -> dict[str, list[str]]:
    """Group detected technologies into functional categories."""
    result: dict[str, list[str]] = {cat: [] for cat in _CATEGORY_MAP}
    for tech in technologies:
        for cat, members in _CATEGORY_MAP.items():
            if any(tech.lower() == m.lower() or m.lower() in tech.lower() for m in members):
                result[cat].append(tech)
    return {k: v for k, v in result.items() if v}  # drop empty categories


def _detect_platform_plan(platform: str | None, technologies: list[str]) -> str | None:
    """Attempt to infer the platform tier/plan from technology signals."""
    if not platform or platform not in _PLATFORM_PLAN_SIGNALS:
        return None
    signals = _PLATFORM_PLAN_SIGNALS[platform]
    for plan, marker in signals.items():
        if any(marker.lower() in t.lower() for t in technologies):
            return plan
    return None


async def analyse_domain(
    domain: str,
    job_id: str = "manual",
) -> TechStackOutput:
    """Run Wappalyzer analysis on a single domain."""
    source = WappalyzerSource()
    tech_result = await source.get_tech_stack(domain)

    categorised = _categorise(tech_result.technologies)
    platform_plan = _detect_platform_plan(tech_result.platform, tech_result.technologies)

    output = TechStackOutput(
        job_id=job_id,
        domain=domain,
        platform=tech_result.platform,
        platform_plan=platform_plan,
        platform_confidence=tech_result.platform_confidence,
        technologies=tech_result.technologies,
        technology_count=tech_result.technology_count,
        categorised=categorised,
        detected_via=tech_result.detected_via,
        as_of=tech_result.as_of,
    )

    # Quality flags
    if output.technology_count == 0:
        output.zero_tech_flagged = True
        log.warning("Agent 5: zero technologies detected for %s", domain)

    if not output.platform:
        output.no_ecom_platform_flagged = True

    log.info(
        "Agent 5 analysed %s: platform=%s tech_count=%d",
        domain,
        output.platform,
        output.technology_count,
    )
    return output


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent5_tech_stack.run_tech_stack",
    bind=True,
    max_retries=3,
    queue="agent5_tech_stack",
)
def run_tech_stack(
    self: Task,
    domain: str,
) -> dict[str, Any]:
    """Celery task entry point for Agent 5."""
    import asyncio

    job_id = str(self.request.id or "local")
    try:
        result = asyncio.get_event_loop().run_until_complete(
            analyse_domain(domain=domain, job_id=job_id)
        )
        return result.model_dump()
    except Exception as exc:
        log.exception("Agent 5 failed for %s: %s", domain, exc)
        countdown = 30 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
