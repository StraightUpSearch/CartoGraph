"""
Agent 6: Intent Scoring

Calculates commercial intent scores using evidence from Agents 1, 2, 4, and 5.
Pure internal calculation — no external API calls.

Schedule: Weekly for all domains.

Scoring formula (from brief):
  commercial_intent_score (1–10) =
    (% keywords with commercial modifiers × 3) +
    (SERP feature presence weight × 2) +
    (product schema detected × 1.5) +
    (paid ads presence × 1) +
    (checkout path detected × 1.5) +
    (merchant listing eligible × 1)
    → normalised to 1–10 scale

SERP feature weights:
  shopping_carousel: 3x | ai_overview: 2x | featured_snippet: 2x |
  sitelinks: 1.5x | people_also_ask: 1x | local_pack: 1x | image_pack: 0.5x
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.config.variables import SERP_FEATURE_WEIGHTS, cg_settings

log = logging.getLogger(__name__)

_MAX_RAW_SCORE = (
    3.0     # modifier component max
    + 3.0   # SERP feature component max (shopping_carousel weight)
    + 1.5   # product schema
    + 1.0   # paid ads
    + 1.5   # checkout path
    + 1.0   # merchant listing eligible
)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class IntentScoringOutput(BaseModel):
    job_id: str
    agent: str = "agent6_intent_scoring"
    schema_version: str = cg_settings.SCHEMA_VERSION
    domain: str
    commercial_intent_score: int = Field(ge=1, le=10)
    percent_traffic_from_intent: dict[str, float] = Field(default_factory=dict)
    shopping_modifier_density: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    raw_score: float = 0.0
    scored_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------


def _serp_feature_score(serp_features: dict[str, bool]) -> float:
    """Compute weighted SERP feature contribution (max = highest single weight)."""
    total = 0.0
    for feature, present in serp_features.items():
        if present:
            weight = SERP_FEATURE_WEIGHTS.get(feature, 0.0)
            total += weight
    # Cap at max single weight to prevent SERP from dominating
    return min(total, max(SERP_FEATURE_WEIGHTS.values()))


def _modifier_density(
    keyword_profile: dict[str, Any],
    modifier_keywords: list[str],
) -> float:
    """
    Fraction of tracked keywords containing commercial modifiers.
    keyword_profile: {"total_keywords": int, "modifier_keyword_count": int}
    """
    total = keyword_profile.get("total_keywords", 0)
    if not total:
        return 0.0
    modifier_count = keyword_profile.get("modifier_keyword_count", 0)
    return min(1.0, modifier_count / total)


def score_domain(
    domain: str,
    keyword_profile: dict[str, Any] | None = None,
    serp_features: dict[str, bool] | None = None,
    technical_signals: dict[str, bool] | None = None,
    traffic_split: dict[str, float] | None = None,
    job_id: str = "manual",
) -> IntentScoringOutput:
    """
    Calculate intent score for a domain from available evidence.

    Parameters
    ----------
    keyword_profile:    From Agent 1/2. Keys: total_keywords, modifier_keyword_count.
    serp_features:      From Agent 2. Keys: shopping_carousel, people_also_ask, etc.
    technical_signals:  From Agent 3/5. Keys: product_schema_detected,
                        checkout_path_detected, paid_ads_seen, merchant_listing_eligible.
    traffic_split:      From Agent 4. Keys: commercial, transactional, shopping (0–1 fractions).
    """
    kw = keyword_profile or {}
    features = serp_features or {}
    signals = technical_signals or {}
    split = traffic_split or {}

    evidence: list[str] = []
    raw_score = 0.0

    # Component 1: keyword modifier density (× 3)
    density = _modifier_density(kw, [])
    kw_contribution = density * 3.0
    raw_score += kw_contribution
    if density > 0:
        evidence.append(f"modifier_density_{density:.2f}")

    # Component 2: SERP feature presence (× 2 multiplier on weighted score)
    serp_contribution = _serp_feature_score(features) * 2.0 / max(SERP_FEATURE_WEIGHTS.values())
    raw_score += serp_contribution
    active_features = [f for f, v in features.items() if v]
    if active_features:
        evidence.append(f"serp_features_{'+'.join(active_features)}")

    # Component 3: product schema detected (× 1.5)
    if signals.get("product_schema_detected"):
        raw_score += 1.5
        evidence.append("product_schema_detected")

    # Component 4: paid ads presence (× 1)
    if signals.get("paid_ads_seen"):
        raw_score += 1.0
        evidence.append("paid_ads_presence")

    # Component 5: checkout path detected (× 1.5)
    if signals.get("checkout_path_detected"):
        raw_score += 1.5
        evidence.append("checkout_path_detected")

    # Component 6: merchant listing eligible (× 1)
    if signals.get("merchant_listing_eligible"):
        raw_score += 1.0
        evidence.append("merchant_listing_eligible")

    # Normalise to 1–10
    normalised = (raw_score / _MAX_RAW_SCORE) * 9 + 1  # maps [0, max] → [1, 10]
    score = max(1, min(10, round(normalised)))

    # Traffic split from Agent 4
    percent_traffic: dict[str, float] = {}
    if split:
        percent_traffic = {
            "commercial": split.get("commercial", 0.0),
            "transactional": split.get("transactional", 0.0),
            "shopping": split.get("shopping", 0.0),
            "source": "internal_calculation",  # type: ignore[assignment]
        }

    log.info(
        "Agent 6 scored %s: intent_score=%d raw=%.2f evidence=%s",
        domain, score, raw_score, evidence,
    )

    return IntentScoringOutput(
        job_id=job_id,
        domain=domain,
        commercial_intent_score=score,
        percent_traffic_from_intent=percent_traffic,
        shopping_modifier_density=round(density, 4),
        evidence=evidence,
        raw_score=round(raw_score, 4),
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent6_intent_scoring.run_intent_scoring",
    bind=True,
    max_retries=3,
    queue="agent6_intent_scoring",
)
def run_intent_scoring(
    self: Task,
    domain: str,
    keyword_profile: dict[str, Any] | None = None,
    serp_features: dict[str, bool] | None = None,
    technical_signals: dict[str, bool] | None = None,
    traffic_split: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Celery task entry point for Agent 6."""
    job_id = str(self.request.id or "local")
    try:
        result = score_domain(
            domain=domain,
            keyword_profile=keyword_profile,
            serp_features=serp_features,
            technical_signals=technical_signals,
            traffic_split=traffic_split,
            job_id=job_id,
        )
        return result.model_dump()
    except Exception as exc:
        log.exception("Agent 6 failed for %s: %s", domain, exc)
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))
