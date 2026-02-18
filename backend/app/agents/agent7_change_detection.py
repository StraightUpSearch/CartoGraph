"""
Agent 7: Change Detection

Computes month-over-month deltas and trending scores for tracked domains.
Writes results to the `change_tracking` JSONB field and pushes snapshots
to ClickHouse for time-series analysis.

Schedule:
  - Monthly: full delta pass over all domains
  - Daily:   trending sample (top 5% by crawl priority) for alert triggers

Trending score formula:
  trending_score = (traffic_delta_pct × 3) + (keyword_wins × 0.1) + (feature_gains × 0.5)
  → capped at 10, normalised to 0–10
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.config.variables import cg_settings

log = logging.getLogger(__name__)

_TRENDING_ALERT_THRESHOLD = 6.0  # trending_score that triggers an alert
_MAX_TRENDING_SCORE = 10.0


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class ChangeDetectionOutput(BaseModel):
    job_id: str
    agent: str = "agent7_change_detection"
    schema_version: str = cg_settings.SCHEMA_VERSION
    domain_id: str
    domain: str
    # Traffic delta
    traffic_delta_absolute: int | None = None
    traffic_delta_percent: float | None = None
    # Keyword position changes
    keyword_wins_last_30d: int = 0
    keyword_losses_last_30d: int = 0
    # SERP feature changes
    feature_gains_last_30d: list[str] = Field(default_factory=list)
    feature_losses_last_30d: list[str] = Field(default_factory=list)
    # Composite score
    trending_score: float = Field(ge=0.0, le=10.0, default=5.0)
    # Alert flag
    alert_triggered: bool = False
    alert_reason: str | None = None
    # Provenance
    current_snapshot_date: str | None = None
    prior_snapshot_date: str | None = None
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------


def _compute_trending_score(
    traffic_delta_pct: float | None,
    keyword_wins: int,
    feature_gains: int,
) -> float:
    """Weighted trending score normalised to 0–10."""
    score = 5.0  # neutral baseline

    if traffic_delta_pct is not None:
        # Each % point of growth ± contributes 0.03
        score += traffic_delta_pct * 0.03

    # Keyword wins/losses contribute ±0.1 each
    score += keyword_wins * 0.1
    score -= keyword_wins * 0.0  # wins offset losses
    score += feature_gains * 0.5

    return round(max(0.0, min(_MAX_TRENDING_SCORE, score)), 2)


def compute_change_delta(
    domain_id: str,
    domain: str,
    current_snapshot: dict[str, Any],
    prior_snapshot: dict[str, Any],
    job_id: str = "manual",
) -> ChangeDetectionOutput:
    """
    Compare current and prior monthly snapshots and compute deltas.

    Snapshots are the `seo_metrics` and `serp_intelligence` JSONB blobs
    stored on the domain record each week by Agents 4 and 2 respectively.
    """
    out = ChangeDetectionOutput(
        job_id=job_id,
        domain_id=domain_id,
        domain=domain,
        current_snapshot_date=current_snapshot.get("as_of"),
        prior_snapshot_date=prior_snapshot.get("as_of"),
    )

    # ------------------------------------------------------------------
    # Traffic delta
    # ------------------------------------------------------------------
    curr_traffic = current_snapshot.get("organic_traffic_estimate")
    prior_traffic = prior_snapshot.get("organic_traffic_estimate")

    if curr_traffic is not None and prior_traffic is not None and prior_traffic > 0:
        out.traffic_delta_absolute = curr_traffic - prior_traffic
        out.traffic_delta_percent = round(
            (curr_traffic - prior_traffic) / prior_traffic, 4
        )

    # ------------------------------------------------------------------
    # Keyword wins / losses (position improvements across tracked keywords)
    # ------------------------------------------------------------------
    curr_kw = current_snapshot.get("top_keywords", []) or []
    prior_kw = prior_snapshot.get("top_keywords", []) or []

    prior_positions: dict[str, int] = {
        kw["query"]: kw.get("position", 100) for kw in prior_kw
    }
    curr_positions: dict[str, int] = {
        kw["query"]: kw.get("position", 100) for kw in curr_kw
    }

    for query, curr_pos in curr_positions.items():
        prior_pos = prior_positions.get(query, 100)
        if curr_pos < prior_pos:
            out.keyword_wins_last_30d += 1
        elif curr_pos > prior_pos:
            out.keyword_losses_last_30d += 1

    # ------------------------------------------------------------------
    # SERP feature changes
    # ------------------------------------------------------------------
    curr_features: dict[str, bool] = (
        current_snapshot.get("serp_features") or {}
    )
    prior_features: dict[str, bool] = (
        prior_snapshot.get("serp_features") or {}
    )

    all_features = set(curr_features) | set(prior_features)
    for feat in all_features:
        curr_val = curr_features.get(feat, False)
        prior_val = prior_features.get(feat, False)
        if curr_val and not prior_val:
            out.feature_gains_last_30d.append(feat)
        elif not curr_val and prior_val:
            out.feature_losses_last_30d.append(feat)

    # ------------------------------------------------------------------
    # Trending score
    # ------------------------------------------------------------------
    out.trending_score = _compute_trending_score(
        traffic_delta_pct=(
            out.traffic_delta_percent * 100 if out.traffic_delta_percent else None
        ),
        keyword_wins=out.keyword_wins_last_30d,
        feature_gains=len(out.feature_gains_last_30d),
    )

    # ------------------------------------------------------------------
    # Alert trigger
    # ------------------------------------------------------------------
    if out.trending_score >= _TRENDING_ALERT_THRESHOLD:
        out.alert_triggered = True
        reasons: list[str] = []
        if out.traffic_delta_percent and out.traffic_delta_percent > 0.1:
            reasons.append(f"traffic_up_{out.traffic_delta_percent:.0%}")
        if out.feature_gains_last_30d:
            reasons.append(f"new_serp_features_{','.join(out.feature_gains_last_30d)}")
        out.alert_reason = "; ".join(reasons) or "trending_score_threshold"
    elif out.trending_score <= (10 - _TRENDING_ALERT_THRESHOLD):
        out.alert_triggered = True
        out.alert_reason = f"declining_score_{out.trending_score}"

    log.info(
        "Agent 7: %s trending_score=%.1f wins=%d losses=%d feature_gains=%s",
        domain,
        out.trending_score,
        out.keyword_wins_last_30d,
        out.keyword_losses_last_30d,
        out.feature_gains_last_30d,
    )
    return out


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent7_change_detection.run_change_detection",
    bind=True,
    max_retries=3,
    queue="agent7_change_detection",
)
def run_change_detection(
    self: Task,
    domain_id: str,
    domain: str,
    current_snapshot: dict[str, Any],
    prior_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Celery task entry point for Agent 7."""
    job_id = str(self.request.id or "local")
    try:
        result = compute_change_delta(
            domain_id=domain_id,
            domain=domain,
            current_snapshot=current_snapshot,
            prior_snapshot=prior_snapshot,
            job_id=job_id,
        )
        return result.model_dump()
    except Exception as exc:
        log.exception("Agent 7 failed for %s: %s", domain, exc)
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))
