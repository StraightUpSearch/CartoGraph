"""
DataForSEO provider implementation

Implements the DataSource interface using DataForSEO's queued SERP API.

Flow for SERP collection (Mode A — preferred):
    1. POST /v3/serp/google/organic/task_post  → returns task IDs
    2. GET  /v3/serp/google/organic/tasks_ready → poll until tasks are ready
    3. GET  /v3/serp/google/organic/task_get/{id} → fetch results

Docs: https://docs.dataforseo.com/v3/serp/overview/
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx

from app.agents.sources.base import (
    BacklinkResult,
    DataSource,
    ProviderError,
    ProviderNotReady,
    ProviderRateLimited,
    SerpResult,
    TechResult,
    _now_utc,
)
from app.config.variables import cg_settings

log = logging.getLogger(__name__)

_SERP_FEATURES_MAP: dict[str, str] = {
    "shopping": "shopping_carousel",
    "people_also_ask": "people_also_ask",
    "featured_snippet": "featured_snippet",
    "local_pack": "local_pack",
    "sitelinks": "sitelinks",
    "images": "image_pack",
    "ai_overview": "ai_overview",
}


def _extract_domain(url: str) -> str:
    """Strip scheme and path from a URL to get the registrable domain."""
    url = url.replace("https://", "").replace("http://", "")
    return url.split("/")[0].lstrip("www.")


class DataForSEOSource(DataSource):
    """
    DataForSEO SERP + Backlinks provider.

    Credentials are loaded from cg_settings (DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD).
    All HTTP calls use httpx with Basic Auth.
    """

    source_id = "dataforseo_serp"

    def __init__(self) -> None:
        self._base = cg_settings.DATAFORSEO_BASE_URL
        self._auth = (cg_settings.DATAFORSEO_LOGIN, cg_settings.DATAFORSEO_PASSWORD)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post(self, path: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=30) as client:
            resp = await client.post(f"{self._base}{path}", json=payload)
        if resp.status_code == 429:
            raise ProviderRateLimited(f"DataForSEO rate limited: {path}")
        if resp.status_code >= 500:
            raise ProviderError(f"DataForSEO server error {resp.status_code}: {path}")
        return resp.json()  # type: ignore[no-any-return]

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self._auth, timeout=30) as client:
            resp = await client.get(f"{self._base}{path}")
        if resp.status_code == 429:
            raise ProviderRateLimited(f"DataForSEO rate limited: {path}")
        if resp.status_code >= 500:
            raise ProviderError(f"DataForSEO server error {resp.status_code}: {path}")
        return resp.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # SERP methods
    # ------------------------------------------------------------------

    async def submit_serp_tasks(
        self,
        keywords: list[str],
        geo: str = "2826",
        language: str = "en",
        device: str = "desktop",
    ) -> list[str]:
        """Submit keywords to DataForSEO queued SERP endpoint."""
        payload = [
            {
                "keyword": kw,
                "location_code": int(geo),
                "language_code": language,
                "device": device,
                "os": "windows",
                "depth": 30,  # fetch top 30 organic results
                "tag": "cartograph",
            }
            for kw in keywords
        ]
        data = await self._post(
            "/v3/serp/google/organic/task_post", payload
        )
        task_ids: list[str] = []
        for item in data.get("tasks", []):
            if item.get("id"):
                task_ids.append(item["id"])
        log.info("Submitted %d SERP tasks to DataForSEO", len(task_ids))
        return task_ids

    async def get_serp_results(self, task_ids: list[str]) -> list[SerpResult]:
        """
        Check tasks_ready endpoint then fetch completed results.
        Raises ProviderNotReady if any tasks are still processing.
        """
        ready_data = await self._get(
            "/v3/serp/google/organic/tasks_ready"
        )
        ready_ids = {t["id"] for t in ready_data.get("tasks", []) or []}

        pending = [tid for tid in task_ids if tid not in ready_ids]
        if pending:
            raise ProviderNotReady(
                f"{len(pending)} SERP tasks still processing"
            )

        results: list[SerpResult] = []
        for tid in task_ids:
            task_data = await self._get(
                f"/v3/serp/google/organic/task_get/regular/{tid}"
            )
            for task in task_data.get("tasks", []):
                keyword = (task.get("data") or {}).get("keyword", "")
                items = (task.get("result") or [{}])[0].get("items") or []
                serp_features: dict[str, bool] = {}
                for feat_raw, feat_key in _SERP_FEATURES_MAP.items():
                    serp_features[feat_key] = any(
                        i.get("type", "").lower() == feat_raw for i in items
                    )
                for item in items:
                    if item.get("type") != "organic":
                        continue
                    url = item.get("url", "")
                    results.append(
                        SerpResult(
                            keyword=keyword,
                            domain=_extract_domain(url),
                            url=url,
                            position=item.get("rank_absolute", 0),
                            serp_features=serp_features,
                            source=self.source_id,
                            raw_payload_hash=hashlib.sha256(
                                json.dumps(task_data, sort_keys=True).encode()
                            ).hexdigest(),
                        )
                    )
        return results

    # ------------------------------------------------------------------
    # Backlink / SEO metrics methods
    # ------------------------------------------------------------------

    async def get_backlink_metrics(
        self, domains: list[str]
    ) -> list[BacklinkResult]:
        """Fetch domain authority and traffic metrics via DataForSEO Backlinks API."""
        payload = [{"target": d, "include_subdomains": False} for d in domains]
        data = await self._post(
            "/v3/backlinks/domain_pages_summary/live", payload
        )
        results: list[BacklinkResult] = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                results.append(
                    BacklinkResult(
                        domain=item.get("target", ""),
                        referring_domains_count=item.get("referring_domains"),
                        backlinks_count=item.get("backlinks"),
                        source=self.source_id,
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Tech stack — DataForSEO does not provide this; delegate to Wappalyzer
    # ------------------------------------------------------------------

    async def get_tech_stack(self, domain: str) -> TechResult:
        raise NotImplementedError(
            "Use WappalyzerSource (Agent 5) for technology detection"
        )
