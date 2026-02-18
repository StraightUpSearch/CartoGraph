"""Add domains table with JSONB enrichment fields

Revision ID: b4e1f2a3c9d8
Revises: 1a31ce608336
Create Date: 2026-02-18 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "b4e1f2a3c9d8"
down_revision = "1a31ce608336"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgcrypto for gen_random_uuid() if not already enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS domains (
            domain_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            domain        VARCHAR(255) NOT NULL UNIQUE,
            country       VARCHAR(2)   NOT NULL DEFAULT 'UK',
            tld           VARCHAR(20),
            status        VARCHAR(20)  DEFAULT 'active',
            first_seen_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            schema_version  VARCHAR(10)  DEFAULT '1.0.0',
            discovery           JSONB,
            ecommerce           JSONB,
            seo_metrics         JSONB,
            intent_layer        JSONB,
            serp_intelligence   JSONB,
            technical_layer     JSONB,
            contact             JSONB,
            marketplace_overlap JSONB,
            paid_ads_presence   JSONB,
            meta                JSONB,
            change_tracking     JSONB,
            confidence_score    JSONB,
            pipeline            JSONB,
            ai_summary          JSONB
        )
        """
    )

    # Scalar indexes for common filter patterns
    op.execute("CREATE INDEX idx_domains_country ON domains(country)")
    op.execute("CREATE INDEX idx_domains_status  ON domains(status)")
    op.execute(
        "CREATE INDEX idx_domains_dr ON domains"
        " ((seo_metrics->>'domain_rating')::int)"
    )
    op.execute(
        "CREATE INDEX idx_domains_traffic ON domains"
        " ((seo_metrics->>'organic_traffic_estimate')::int)"
    )
    op.execute(
        "CREATE INDEX idx_domains_intent ON domains"
        " ((intent_layer->>'commercial_intent_score')::int)"
    )
    op.execute(
        "CREATE INDEX idx_domains_platform ON domains"
        " ((ecommerce->>'platform'))"
    )
    op.execute(
        "CREATE INDEX idx_domains_category ON domains"
        " ((ecommerce->>'category_primary'))"
    )

    # GIN indexes for JSONB filtering
    op.execute(
        "CREATE INDEX idx_domains_discovery_gin ON domains USING GIN (discovery)"
    )
    op.execute(
        "CREATE INDEX idx_domains_serp_features_gin ON domains USING GIN (serp_intelligence)"
    )
    op.execute(
        "CREATE INDEX idx_domains_tech_gin ON domains USING GIN (technical_layer)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS domains")
