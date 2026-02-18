"""
Agent 1: Keyword Miner

Generates and maintains the UK commercial keyword set ([KEYWORD_SET]) by
combining intent modifiers with product category terms.

Schedule: Weekly refresh of full keyword queue; daily rotation of query batches.

Formula:  [INTENT_MODIFIER] + [PRODUCT_CATEGORY] + [GEO_MODIFIER]

Output: JSON-serialisable KeywordMinerOutput Pydantic model.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.config.variables import UK_INTENT_MODIFIERS, VARIABLES, cg_settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema — canonical, JSON-serialisable
# ---------------------------------------------------------------------------


class KeywordItem(BaseModel):
    keyword: str
    cluster_id: str
    intent_type: str
    priority_score: int = Field(ge=1, le=10)
    modifiers_present: list[str]
    rationale: str


class KeywordMinerOutput(BaseModel):
    job_id: str
    agent: str = "agent1_keyword_miner"
    schema_version: str = cg_settings.SCHEMA_VERSION
    country: str = cg_settings.DEFAULT_COUNTRY
    generated_at: str
    keywords: list[KeywordItem]
    total_count: int
    batch_index: int = 0


# ---------------------------------------------------------------------------
# Core keyword generation logic
# ---------------------------------------------------------------------------

# Priority product categories — Phase 1 seed list (200 categories)
# In production these will be loaded from the Google Product Taxonomy UK file.
_SEED_CATEGORIES: list[dict[str, Any]] = [
    {"name": "running shoes", "cluster_id": "footwear_running", "priority": 9},
    {"name": "gym wear", "cluster_id": "apparel_activewear", "priority": 8},
    {"name": "supplements", "cluster_id": "health_supplements", "priority": 8},
    {"name": "dog food", "cluster_id": "pets_food", "priority": 7},
    {"name": "laptop bags", "cluster_id": "bags_laptop", "priority": 7},
    {"name": "coffee machines", "cluster_id": "appliances_coffee", "priority": 8},
    {"name": "skincare", "cluster_id": "beauty_skincare", "priority": 8},
    {"name": "garden furniture", "cluster_id": "garden_outdoor", "priority": 7},
    {"name": "baby clothes", "cluster_id": "baby_clothing", "priority": 7},
    {"name": "yoga mats", "cluster_id": "fitness_yoga", "priority": 6},
]


def _modifiers_for_intent(intent_type: str) -> list[str]:
    return UK_INTENT_MODIFIERS.get(intent_type, [])


def _build_keyword(modifier: str, category: str, geo: str = "UK") -> str:
    """Combine modifier + product + geo into a search query string."""
    if "{product}" in modifier:
        return modifier.replace("{product}", category)
    parts = [modifier, category, geo]
    return " ".join(p for p in parts if p)


def generate_keyword_batch(
    max_keywords: int = 1000,
    batch_index: int = 0,
    job_id: str = "manual",
) -> KeywordMinerOutput:
    """
    Generate a batch of commercial intent keywords.

    In production this function reads product categories from PostgreSQL
    (keywords table) and cycles through them. For Phase 1 it uses the
    seed list above.
    """
    items: list[KeywordItem] = []

    for category_info in _SEED_CATEGORIES:
        cat = category_info["name"]
        cluster_id = category_info["cluster_id"]
        base_priority = category_info["priority"]

        for intent_type, modifiers in UK_INTENT_MODIFIERS.items():
            for mod in modifiers:
                kw = _build_keyword(mod, cat)
                # Transactional modifiers get highest priority
                priority = (
                    min(10, base_priority + 1)
                    if intent_type == "transactional"
                    else base_priority
                )
                items.append(
                    KeywordItem(
                        keyword=kw,
                        cluster_id=cluster_id,
                        intent_type=intent_type,
                        priority_score=priority,
                        modifiers_present=_detect_modifiers(kw),
                        rationale=f"{intent_type} intent; {cat} category",
                    )
                )
                if len(items) >= max_keywords:
                    break
            if len(items) >= max_keywords:
                break
        if len(items) >= max_keywords:
            break

    log.info(
        "Agent 1 generated %d keywords for batch %d",
        len(items),
        batch_index,
    )

    return KeywordMinerOutput(
        job_id=job_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        keywords=items,
        total_count=len(items),
        batch_index=batch_index,
    )


def _detect_modifiers(keyword: str) -> list[str]:
    """Identify which intent modifiers appear in a keyword string."""
    found: list[str] = []
    kw_lower = keyword.lower()
    all_modifiers = [
        m
        for mods in UK_INTENT_MODIFIERS.values()
        for m in mods
        if "{product}" not in m
    ]
    for mod in all_modifiers:
        if mod.lower() in kw_lower:
            found.append(mod)
    if "uk" in kw_lower:
        found.append("uk")
    return list(set(found))


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.agents.agent1_keyword_miner.run_keyword_miner",
    bind=True,
    max_retries=3,
    queue="agent1_keyword_miner",
)
def run_keyword_miner(
    self: Task,
    batch_index: int = 0,
    max_keywords: int = 1000,
) -> dict[str, Any]:
    """
    Celery task entry point for Agent 1.

    Returns the KeywordMinerOutput as a plain dict (JSON-serialisable).
    """
    job_id = self.request.id or "local"
    try:
        result = generate_keyword_batch(
            max_keywords=max_keywords,
            batch_index=batch_index,
            job_id=str(job_id),
        )
        return result.model_dump()
    except Exception as exc:
        log.exception("Agent 1 failed on batch %d: %s", batch_index, exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
