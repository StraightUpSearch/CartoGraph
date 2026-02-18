"""
Agent 3: Domain Classifier

Determines if a discovered domain is a genuine ecommerce store vs a blog,
directory, news site, or other non-store.

CRITICAL: Run this BEFORE Agents 4 and 5 to avoid wasting API budget on
non-ecommerce domains.

Ecommerce validation signals (evidence-based):
  - Product structured data (Product, Offer schemas)
  - Checkout path detection (/cart, /checkout URL patterns)
  - Ecommerce platform fingerprints (Shopify, WooCommerce, Magento)
  - Commercial SERP presence (ranking for transactional queries)
  - Payment provider scripts detected
  - Merchant listing eligible structured data

Output: JSON-serialisable DomainClassifierOutput Pydantic model with
evidence list + confidence score (always explainable).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.config.variables import cg_settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class DomainClassifierOutput(BaseModel):
    job_id: str
    agent: str = "agent3_domain_classifier"
    schema_version: str = cg_settings.SCHEMA_VERSION
    domain: str
    is_ecommerce: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]
    exclusions_triggered: list[str]
    classified_at: str


# ---------------------------------------------------------------------------
# Detection signal patterns
# ---------------------------------------------------------------------------

# Checkout / cart URL patterns
_CHECKOUT_PATTERNS = re.compile(
    r"/(cart|checkout|basket|bag|order|buy|purchase|shop|store)",
    re.IGNORECASE,
)

# Ecommerce platform fingerprints detectable from HTML/HTTP headers
_PLATFORM_SIGNATURES: dict[str, list[str]] = {
    "shopify": [
        "cdn.shopify.com",
        "myshopify.com",
        "Shopify.theme",
        "window.Shopify",
        "/checkouts/",
    ],
    "woocommerce": [
        "woocommerce",
        "wc-ajax",
        "add-to-cart",
        "wc_add_to_cart_params",
    ],
    "magento": [
        "Mage.Cookies",
        "Magento_Ui",
        "mage/translate",
        "/checkout/cart/add",
    ],
    "bigcommerce": [
        "cdn11.bigcommerce.com",
        "BigCommerce.callbacks",
        "/cart.php",
    ],
    "squarespace": [
        "squarespace-cdn.com",
        "static1.squarespace.com",
        "data-content-field",
    ],
    "wix": [
        "static.wixstatic.com",
        "wix-code-sdk",
        "corvid-sdk",
    ],
    "prestashop": [
        "PrestaShop",
        "/module/aeuc_front/",
        "/index.php?controller=cart",
    ],
}

# Product structured data markers
_PRODUCT_SCHEMA_MARKERS = [
    '"@type":"Product"',
    '"@type": "Product"',
    'type="application/ld+json"',
    'itemtype="https://schema.org/Product"',
    'itemtype="http://schema.org/Product"',
]

# Payment provider script markers
_PAYMENT_MARKERS = [
    "stripe.com/v3",
    "js.braintreegateway.com",
    "paypal.com/sdk",
    "klarna.com/uk",
    "sagepay",
    "worldpay",
    "checkout.com",
]

# Signals that suggest NOT an ecommerce store
_EXCLUSION_SIGNALS: dict[str, list[str]] = {
    "is_news_site": ["<meta name=\"news_keywords\"", "article:published_time", "og:type\" content=\"article\""],
    "is_directory": ["/directory/", "/listing/", "business-directory", "find-a-"],
    "is_blog_only": ["wp-content/themes/", "blogspot.com", "medium.com"],
    "is_forum": ["vBulletin", "phpBB", "XenForo", "Discourse"],
}


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


def classify_domain(
    domain: str,
    html_content: str = "",
    response_headers: dict[str, str] | None = None,
    sample_urls: list[str] | None = None,
    serp_evidence: dict[str, Any] | None = None,
) -> DomainClassifierOutput:
    """
    Classify a domain as ecommerce or not using available signals.

    Parameters
    ----------
    domain:           The domain being classified.
    html_content:     Raw HTML from the domain's homepage (may be empty in
                      stub/test mode).
    response_headers: HTTP response headers (used for platform detection).
    sample_urls:      URLs from sitemap or SERP results for this domain.
    serp_evidence:    Dict from Agent 2 output (serp_features, position, etc).
    """
    evidence: list[str] = []
    exclusions: list[str] = []
    headers = response_headers or {}
    urls = sample_urls or []
    serp = serp_evidence or {}
    html = html_content

    # ------------------------------------------------------------------
    # Positive signals
    # ------------------------------------------------------------------

    # 1. Platform fingerprints
    detected_platform: str | None = None
    for platform, signatures in _PLATFORM_SIGNATURES.items():
        if any(sig.lower() in html.lower() for sig in signatures):
            evidence.append(f"{platform}_platform_fingerprint")
            detected_platform = platform
            break

    # X-Powered-By / Server headers
    powered_by = headers.get("X-Powered-By", "").lower()
    if "woocommerce" in powered_by or "shopify" in powered_by:
        evidence.append("platform_detected_via_header")

    # 2. Product schema
    if any(marker.lower() in html.lower() for marker in _PRODUCT_SCHEMA_MARKERS):
        evidence.append("product_schema_detected")

    # 3. Checkout / cart URL patterns in sample URLs or HTML
    has_checkout = bool(_CHECKOUT_PATTERNS.search(html)) or any(
        _CHECKOUT_PATTERNS.search(u) for u in urls
    )
    if has_checkout:
        evidence.append("checkout_path_detected")

    # 4. Payment provider scripts
    if any(p.lower() in html.lower() for p in _PAYMENT_MARKERS):
        evidence.append("payment_provider_script_detected")

    # 5. Commercial SERP presence from Agent 2
    if serp.get("shopping_carousel"):
        evidence.append("commercial_serp_presence_shopping_carousel")
    if serp.get("position", 99) <= 10:
        evidence.append("commercial_serp_presence_top10")

    # ------------------------------------------------------------------
    # Exclusion signals (these reduce or negate the ecommerce verdict)
    # ------------------------------------------------------------------

    for exclusion_name, markers in _EXCLUSION_SIGNALS.items():
        if any(m.lower() in html.lower() for m in markers):
            exclusions.append(exclusion_name)

    # ------------------------------------------------------------------
    # Confidence calculation
    # ------------------------------------------------------------------

    positive_score = len(evidence)
    exclusion_penalty = len(exclusions) * 0.25

    # Weighted: platform detection + product schema + checkout = core signals
    if detected_platform:
        positive_score += 1
    if "product_schema_detected" in evidence and "checkout_path_detected" in evidence:
        positive_score += 1  # bonus for dual signal

    raw_confidence = min(1.0, (positive_score * 0.2) - exclusion_penalty)
    confidence = max(0.0, raw_confidence)
    is_ecommerce = confidence >= 0.4 and len(exclusions) < 2

    log.info(
        "Agent 3 classified %s: is_ecommerce=%s confidence=%.2f evidence=%s",
        domain,
        is_ecommerce,
        confidence,
        evidence,
    )

    return DomainClassifierOutput(
        job_id="inline",
        domain=domain,
        is_ecommerce=is_ecommerce,
        confidence=confidence,
        evidence=evidence,
        exclusions_triggered=exclusions,
        classified_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent3_domain_classifier.classify_domain_task",
    bind=True,
    max_retries=3,
    queue="agent3_domain_classifier",
)
def classify_domain_task(
    self: Task,
    domain: str,
    html_content: str = "",
    response_headers: dict[str, str] | None = None,
    sample_urls: list[str] | None = None,
    serp_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Celery task entry point for Agent 3.

    The orchestrator should pass html_content fetched from the domain's
    homepage (via crawl4ai or direct httpx request) and any SERP evidence
    from the Agent 2 result for this domain.
    """
    job_id = str(self.request.id or "local")

    try:
        result = classify_domain(
            domain=domain,
            html_content=html_content,
            response_headers=response_headers,
            sample_urls=sample_urls,
            serp_evidence=serp_evidence,
        )
        result.job_id = job_id
        return result.model_dump()
    except Exception as exc:
        log.exception("Agent 3 failed for domain %s: %s", domain, exc)
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))
