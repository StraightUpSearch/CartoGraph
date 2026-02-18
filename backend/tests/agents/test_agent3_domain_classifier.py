"""Tests for Agent 3: Domain Classifier"""

import json

import pytest

from app.agents.agent3_domain_classifier import (
    DomainClassifierOutput,
    classify_domain,
)


# ---------------------------------------------------------------------------
# Fixtures — representative HTML snippets
# ---------------------------------------------------------------------------

SHOPIFY_HTML = """
<html>
<head><script>window.Shopify = {}</script></head>
<body>
<script src="https://cdn.shopify.com/s/files/1/theme.js"></script>
<script type="application/ld+json">{"@type":"Product","name":"Running Shoe"}</script>
<a href="/cart">Cart</a>
<a href="/checkout">Checkout</a>
<script src="https://js.stripe.com/v3/"></script>
</body>
</html>
"""

BLOG_HTML = """
<html>
<head><meta name="news_keywords" content="sport, running"/></head>
<body>
<article>
<meta property="article:published_time" content="2026-02-01"/>
<p>Best running tips for beginners.</p>
</article>
</body>
</html>
"""

WOOCOMMERCE_HTML = """
<html>
<body>
<script>var wc_add_to_cart_params = {}</script>
<div class="woocommerce">
<a href="/cart">View Cart</a>
</div>
<script type="application/ld+json">{"@type":"Product"}</script>
</body>
</html>
"""

MINIMAL_HTML = "<html><body><p>Hello world</p></body></html>"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_shopify_store_classified_as_ecommerce() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert result.is_ecommerce is True
    assert result.confidence >= 0.4
    assert "shopify_platform_fingerprint" in result.evidence


def test_product_schema_detected() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert "product_schema_detected" in result.evidence


def test_checkout_path_detected() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert "checkout_path_detected" in result.evidence


def test_payment_provider_detected() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert "payment_provider_script_detected" in result.evidence


def test_blog_not_classified_as_ecommerce() -> None:
    result = classify_domain("blog.example.com", html_content=BLOG_HTML)
    assert result.is_ecommerce is False
    assert "is_news_site" in result.exclusions_triggered


def test_woocommerce_store_classified_as_ecommerce() -> None:
    result = classify_domain("shop.co.uk", html_content=WOOCOMMERCE_HTML)
    assert result.is_ecommerce is True
    assert "woocommerce_platform_fingerprint" in result.evidence


def test_minimal_html_low_confidence() -> None:
    result = classify_domain("unknown.co.uk", html_content=MINIMAL_HTML)
    assert result.confidence < 0.4


def test_serp_evidence_boosts_confidence() -> None:
    result_without = classify_domain("example.co.uk", html_content=MINIMAL_HTML)
    result_with = classify_domain(
        "example.co.uk",
        html_content=MINIMAL_HTML,
        serp_evidence={"shopping_carousel": True, "position": 3},
    )
    assert result_with.confidence >= result_without.confidence


def test_output_schema_version() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert result.schema_version == "1.0.0"


def test_evidence_is_non_empty_for_ecommerce() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert len(result.evidence) > 0


def test_output_is_json_serialisable() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    json.dumps(result.model_dump())


def test_classified_at_is_set() -> None:
    result = classify_domain("example.co.uk", html_content=SHOPIFY_HTML)
    assert result.classified_at  # non-empty ISO timestamp


def test_domain_field_preserved() -> None:
    result = classify_domain("myshop.co.uk", html_content=SHOPIFY_HTML)
    assert result.domain == "myshop.co.uk"
