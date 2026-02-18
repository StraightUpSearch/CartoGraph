"""
Moz Links API source

Provides Domain Authority (DA), Page Authority (PA), and Spam Score.
Used as a supplementary authority signal alongside DataForSEO DR.

Auth: HMAC-SHA1 (access_id + secret_key + expiry timestamp)
Docs: https://moz.com/help/links-api

Used by: Agent 4 (SEO Metrics)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from base64 import b64encode

import httpx

from app.agents.sources.base import (
    BacklinkResult,
    DataSource,
    ProviderError,
    ProviderRateLimited,
    SerpResult,
    TechResult,
)
from app.config.variables import cg_settings

log = logging.getLogger(__name__)

_MOZ_API_BASE = "https://lsapi.seomoz.com/v2"


class MozSource(DataSource):
    """
    Moz Links API implementation.

    Returns DA, PA, Spam Score for domains.
    Cross-checked against DataForSEO DR in Agent 4 to detect anomalies.
    """

    source_id = "moz_api"

    def __init__(self) -> None:
        self._access_id = cg_settings.MOZ_ACCESS_ID
        self._secret = cg_settings.MOZ_SECRET_KEY

    def _auth_header(self) -> str:
        expiry = int(time.time()) + 300  # 5-minute window
        str_to_sign = f"{self._access_id}\n{expiry}"
        signature = b64encode(
            hmac.new(
                self._secret.encode("utf-8"),
                str_to_sign.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return f"Basic {b64encode(f'{self._access_id}:{expiry}:{signature}'.encode()).decode()}"

    async def get_backlink_metrics(
        self, domains: list[str]
    ) -> list[BacklinkResult]:
        """Fetch DA, PA, Spam Score for a batch of domains."""
        results: list[BacklinkResult] = []

        # Moz URL Metrics endpoint processes one target per request
        for domain in domains:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        f"{_MOZ_API_BASE}/url_metrics",
                        headers={
                            "Authorization": self._auth_header(),
                            "Content-Type": "application/json",
                        },
                        json={"targets": [f"{domain}/"], "metrics": ["domain_authority", "page_authority", "spam_score"]},
                    )
                if resp.status_code == 429:
                    raise ProviderRateLimited("Moz API rate limited")
                if resp.status_code >= 500:
                    raise ProviderError(f"Moz API error {resp.status_code}")

                data = resp.json()
                for item in data.get("results", []):
                    results.append(
                        BacklinkResult(
                            domain=domain,
                            domain_authority=int(item.get("domain_authority", 0)),
                            page_authority=int(item.get("page_authority", 0)),
                            spam_score=int(item.get("spam_score", 0)),
                            source=self.source_id,
                        )
                    )
            except (ProviderRateLimited, ProviderError):
                raise
            except Exception as exc:
                log.warning("Moz API failed for %s: %s", domain, exc)

        return results

    # ------------------------------------------------------------------
    # Not implemented — Moz doesn't provide SERP or tech data
    # ------------------------------------------------------------------

    async def submit_serp_tasks(self, keywords: list[str], **_: object) -> list[str]:
        raise NotImplementedError("MozSource does not provide SERP data")

    async def get_serp_results(self, task_ids: list[str]) -> list[SerpResult]:
        raise NotImplementedError("MozSource does not provide SERP data")

    async def get_tech_stack(self, domain: str) -> TechResult:
        raise NotImplementedError("MozSource does not provide tech stack data")
