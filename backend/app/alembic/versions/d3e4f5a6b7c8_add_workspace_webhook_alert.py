"""Add workspace, webhook_endpoint, alert, and api_token tables

Revision ID: d3e4f5a6b7c8
Revises: b4e1f2a3c9d8
Create Date: 2026-02-18 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "b4e1f2a3c9d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # workspaces — one per team; owns the API token and tier
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace (
            workspace_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(255) NOT NULL,
            owner_id        UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            tier            VARCHAR(20) NOT NULL DEFAULT 'free',
            -- API token (hashed, like a password)
            api_token_hash  VARCHAR(255),
            api_token_prefix VARCHAR(16),   -- first 8 chars for display (e.g. cg_abc123)
            -- Monthly usage counters — reset each billing cycle
            domain_lookups_used     INT NOT NULL DEFAULT 0,
            export_credits_used     INT NOT NULL DEFAULT 0,
            api_calls_used          INT NOT NULL DEFAULT 0,
            billing_cycle_start     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            -- Metadata
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_workspace_owner ON workspace(owner_id)")
    op.execute("CREATE INDEX idx_workspace_tier  ON workspace(tier)")

    # -----------------------------------------------------------------
    # webhook_endpoints — user-configured delivery targets
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_endpoint (
            webhook_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id    UUID NOT NULL REFERENCES workspace(workspace_id) ON DELETE CASCADE,
            url             VARCHAR(2048) NOT NULL,
            secret          VARCHAR(255) NOT NULL,   -- HMAC signing secret
            event_types     TEXT[] NOT NULL DEFAULT '{}',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_webhook_workspace ON webhook_endpoint(workspace_id)")

    # -----------------------------------------------------------------
    # webhook_deliveries — delivery audit log (30-day retention)
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_delivery (
            delivery_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            webhook_id      UUID NOT NULL REFERENCES webhook_endpoint(webhook_id) ON DELETE CASCADE,
            event_type      VARCHAR(64) NOT NULL,
            payload         JSONB NOT NULL,
            response_status INT,
            response_body   TEXT,
            attempt_count   INT NOT NULL DEFAULT 1,
            delivered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            success         BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute("CREATE INDEX idx_delivery_webhook ON webhook_delivery(webhook_id)")

    # -----------------------------------------------------------------
    # alerts — saved alert configurations per workspace
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alert (
            alert_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id    UUID NOT NULL REFERENCES workspace(workspace_id) ON DELETE CASCADE,
            name            VARCHAR(255) NOT NULL,
            alert_type      VARCHAR(64) NOT NULL,   -- new_domain | tech_change | dr_change | serp_feature
            filter_criteria JSONB,                  -- domain filters that trigger alert
            threshold       JSONB,                  -- threshold conditions
            delivery        JSONB,                  -- email | webhook | slack config
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            last_triggered  TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_alert_workspace ON alert(workspace_id)")
    op.execute("CREATE INDEX idx_alert_type      ON alert(alert_type)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert")
    op.execute("DROP TABLE IF EXISTS webhook_delivery")
    op.execute("DROP TABLE IF EXISTS webhook_endpoint")
    op.execute("DROP TABLE IF EXISTS workspace")
