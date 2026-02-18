"""
Wappalyzer source — technology fingerprinting via self-hosted Wappalyzer

Uses python-Wappalyzer (MIT) with Playwright headless Chromium for JS rendering.
Falls back to HTTP-only analysis when Playwright is unavailable.

Capacity: 3 worker instances → ~15,000 domains/day at bi-weekly cadence.

Dependencies:
  pip install python-Wappalyzer playwright
  playwright install chromium

Used by: Agent 5 (Tech Stack Analyser)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agents.sources.base import (
    DataSource,
    BacklinkResult,
    ProviderError,
    SerpResult,
    TechResult,
)

log = logging.getLogger(__name__)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class WappalyzerSource(DataSource):
    """
    Technology detection using python-Wappalyzer + Playwright.

    Detection pipeline:
      1. Navigate to domain root with Playwright (5s JS execution timeout)
      2. Pass rendered HTML + HTTP headers + cookies to Wappalyzer analyser
      3. Filter results: confidence >= 0.5 required to record
      4. Classify technologies into functional categories
    """

    source_id = "wappalyzer_self_hosted"

    async def get_tech_stack(self, domain: str) -> TechResult:  # noqa: C901
        """
        Fingerprint a domain's technology stack.

        Tries Playwright first; falls back to requests-based analysis.
        Raises ProviderError if both fail.
        """
        url = f"https://{domain}"

        # ------------------------------------------------------------------
        # Attempt 1: Playwright + python-Wappalyzer (full JS rendering)
        # ------------------------------------------------------------------
        try:
            return await self._detect_with_playwright(domain, url)
        except ImportError:
            log.warning("Playwright or python-Wappalyzer not installed; using HTTP fallback")
        except Exception as exc:
            log.warning("Playwright detection failed for %s: %s", domain, exc)

        # ------------------------------------------------------------------
        # Attempt 2: HTTP-only (no JS rendering)
        # ------------------------------------------------------------------
        try:
            return await self._detect_with_httpx(domain, url)
        except Exception as exc:
            raise ProviderError(f"Tech detection failed for {domain}: {exc}") from exc

    async def _detect_with_playwright(self, domain: str, url: str) -> TechResult:
        """Full detection: JS-rendered page via Playwright."""
        from playwright.async_api import async_playwright  # type: ignore[import]
        from Wappalyzer import Wappalyzer, WebPage  # type: ignore[import]

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                response = await page.goto(url, timeout=15000, wait_until="networkidle")
                html = await page.content()
                headers: dict[str, str] = {}
                if response:
                    headers = dict(response.headers)
            finally:
                await browser.close()

        wappalyzer = Wappalyzer.latest()
        webpage = WebPage(url, html, headers)
        detected = wappalyzer.analyze_with_versions_and_categories(webpage)

        return self._build_result(domain, detected)

    async def _detect_with_httpx(self, domain: str, url: str) -> TechResult:
        """Fallback: HTTP headers + static HTML only."""
        import httpx
        from Wappalyzer import Wappalyzer, WebPage  # type: ignore[import]

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)

        wappalyzer = Wappalyzer.latest()
        webpage = WebPage(url, resp.text, dict(resp.headers))
        detected = wappalyzer.analyze_with_versions_and_categories(webpage)

        return self._build_result(domain, detected)

    def _build_result(
        self, domain: str, detected: dict[str, dict[str, object]]
    ) -> TechResult:
        """Convert Wappalyzer output to TechResult."""
        # Wappalyzer returns {name: {"version": ..., "categories": [...], "confidence": ...}}
        # Filter to confidence >= 0.5
        tech_names: list[str] = []
        platform: str | None = None
        platform_confidence: float = 0.0

        ecom_categories = {"ecommerce", "cms", "e-commerce"}

        for name, info in detected.items():
            confidence = float(info.get("confidence", 100)) / 100  # Wappalyzer uses 0-100
            if confidence < 0.5:
                continue
            tech_names.append(name)
            categories = [str(c).lower() for c in (info.get("categories") or [])]
            if any(c in ecom_categories for c in categories):
                if confidence > platform_confidence:
                    platform = name
                    platform_confidence = confidence

        return TechResult(
            domain=domain,
            platform=platform,
            platform_confidence=platform_confidence,
            technologies=tech_names,
            technology_count=len(tech_names),
            detected_via=self.source_id,
            as_of=_now_utc(),
        )

    # ------------------------------------------------------------------
    # Not implemented — Wappalyzer only does tech detection
    # ------------------------------------------------------------------

    async def submit_serp_tasks(self, keywords: list[str], **_: object) -> list[str]:
        raise NotImplementedError

    async def get_serp_results(self, task_ids: list[str]) -> list[SerpResult]:
        raise NotImplementedError

    async def get_backlink_metrics(self, domains: list[str]) -> list[BacklinkResult]:
        raise NotImplementedError
