"""
ClickHouse client and schema definitions

ClickHouse Cloud receives time-series metrics from PostgreSQL via PeerDB CDC.
This module also handles direct writes from Agents 4 and 7 for snapshot storage.

Tables (managed in ClickHouse, not Alembic):
  - domain_metrics_history    — weekly DR, traffic, keywords, backlinks snapshots
  - serp_snapshots            — per-keyword SERP results with feature flags
  - technology_changelog      — platform and tech stack change events

Setup:
  1. Provision ClickHouse Cloud instance
  2. Set CLICKHOUSE_HOST, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD in .env
  3. Run create_tables() once to initialise the schema
  4. Configure PeerDB CDC from PostgreSQL domains table → ClickHouse

Docs: https://clickhouse.com/docs/en/integrations/python
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection settings
# ---------------------------------------------------------------------------

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8443"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "cartograph")

# ---------------------------------------------------------------------------
# Table DDL
# ---------------------------------------------------------------------------

CREATE_DOMAIN_METRICS_HISTORY = f"""
CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DATABASE}.domain_metrics_history (
    domain_id        UUID,
    domain           String,
    country          FixedString(2),
    snapshot_date    Date,
    domain_rating    Nullable(Int16),
    domain_authority Nullable(Int16),
    spam_score       Nullable(Int16),
    organic_traffic  Nullable(Int64),
    keywords_count   Nullable(Int64),
    backlinks_count  Nullable(Int64),
    referring_domains Nullable(Int64),
    source           LowCardinality(String)
)
ENGINE = ReplacingMergeTree(snapshot_date)
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (domain_id, snapshot_date)
"""

CREATE_SERP_SNAPSHOTS = f"""
CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DATABASE}.serp_snapshots (
    keyword              String,
    domain               String,
    country              FixedString(2),
    position             Int16,
    shopping_carousel    Bool DEFAULT false,
    people_also_ask      Bool DEFAULT false,
    featured_snippet     Bool DEFAULT false,
    local_pack           Bool DEFAULT false,
    sitelinks            Bool DEFAULT false,
    image_pack           Bool DEFAULT false,
    ai_overview          Bool DEFAULT false,
    fetched_at           DateTime,
    source               LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(fetched_at)
ORDER BY (domain, keyword, fetched_at)
TTL fetched_at + INTERVAL 2 YEAR
"""

CREATE_TECHNOLOGY_CHANGELOG = f"""
CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DATABASE}.technology_changelog (
    domain_id    UUID,
    domain       String,
    field        String,
    old_value    Nullable(String),
    new_value    Nullable(String),
    detected_at  DateTime
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(detected_at)
ORDER BY (domain_id, detected_at)
"""

ALL_DDL = [
    f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DATABASE}",
    CREATE_DOMAIN_METRICS_HISTORY,
    CREATE_SERP_SNAPSHOTS,
    CREATE_TECHNOLOGY_CHANGELOG,
]

# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------


def get_client() -> Any:
    """
    Return a clickhouse_connect client.
    Raises ImportError if clickhouse-connect is not installed.
    Raises RuntimeError if CLICKHOUSE_HOST is not configured.
    """
    try:
        import clickhouse_connect  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "Install clickhouse-connect: uv add clickhouse-connect"
        ) from exc

    if not CLICKHOUSE_HOST:
        raise RuntimeError(
            "CLICKHOUSE_HOST is not set. Provision a ClickHouse Cloud instance "
            "and add the connection details to .env"
        )

    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        secure=True,
    )


def create_tables() -> None:
    """Run all DDL statements to initialise the ClickHouse schema."""
    client = get_client()
    for ddl in ALL_DDL:
        log.info("ClickHouse DDL: %s", ddl[:60])
        client.command(ddl)
    log.info("ClickHouse schema initialised in database '%s'", CLICKHOUSE_DATABASE)


# ---------------------------------------------------------------------------
# Write helpers — called by Agents 4 and 7
# ---------------------------------------------------------------------------


def insert_domain_metrics_snapshot(
    domain_id: str,
    domain: str,
    country: str,
    snapshot_date: str,
    metrics: dict[str, Any],
    source: str = "dataforseo",
) -> None:
    """Insert a single domain metrics snapshot row."""
    try:
        client = get_client()
        client.insert(
            f"{CLICKHOUSE_DATABASE}.domain_metrics_history",
            [
                [
                    domain_id,
                    domain,
                    country[:2],
                    snapshot_date,
                    metrics.get("domain_rating"),
                    metrics.get("domain_authority"),
                    metrics.get("spam_score"),
                    metrics.get("organic_traffic_estimate"),
                    metrics.get("organic_keywords_count"),
                    metrics.get("backlinks_count"),
                    metrics.get("referring_domains_count"),
                    source,
                ]
            ],
            column_names=[
                "domain_id", "domain", "country", "snapshot_date",
                "domain_rating", "domain_authority", "spam_score",
                "organic_traffic", "keywords_count", "backlinks_count",
                "referring_domains", "source",
            ],
        )
    except Exception as exc:
        # ClickHouse is non-critical for MVP — log and continue
        log.error("ClickHouse insert failed for %s: %s", domain, exc)


def insert_serp_snapshot(rows: list[dict[str, Any]]) -> None:
    """Batch insert SERP snapshot rows."""
    if not rows:
        return
    try:
        client = get_client()
        client.insert(
            f"{CLICKHOUSE_DATABASE}.serp_snapshots",
            [
                [
                    r["keyword"], r["domain"], r.get("country", "UK"),
                    r.get("position", 0),
                    r.get("shopping_carousel", False),
                    r.get("people_also_ask", False),
                    r.get("featured_snippet", False),
                    r.get("local_pack", False),
                    r.get("sitelinks", False),
                    r.get("image_pack", False),
                    r.get("ai_overview", False),
                    r.get("fetched_at"), r.get("source", "dataforseo"),
                ]
                for r in rows
            ],
            column_names=[
                "keyword", "domain", "country", "position",
                "shopping_carousel", "people_also_ask", "featured_snippet",
                "local_pack", "sitelinks", "image_pack", "ai_overview",
                "fetched_at", "source",
            ],
        )
    except Exception as exc:
        log.error("ClickHouse SERP insert failed: %s", exc)


def insert_tech_changelog(
    domain_id: str,
    domain: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
    detected_at: str,
) -> None:
    """Log a technology stack change event."""
    try:
        client = get_client()
        client.insert(
            f"{CLICKHOUSE_DATABASE}.technology_changelog",
            [[domain_id, domain, field, old_value, new_value, detected_at]],
            column_names=["domain_id", "domain", "field", "old_value", "new_value", "detected_at"],
        )
    except Exception as exc:
        log.error("ClickHouse tech changelog insert failed for %s: %s", domain, exc)
