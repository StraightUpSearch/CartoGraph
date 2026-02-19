"""
Alembic migration: add Stripe billing columns to workspace table
+ create founding_member_count singleton table

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-02-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Stripe billing columns on workspace ---
    op.add_column(
        "workspace",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "workspace",
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "stripe_subscription_status",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "stripe_price_id",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "founding_member",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # Unique constraints for Stripe IDs (one subscription per workspace)
    op.create_index(
        "ix_workspace_stripe_customer_id",
        "workspace",
        ["stripe_customer_id"],
        unique=True,
    )
    op.create_index(
        "ix_workspace_stripe_subscription_id",
        "workspace",
        ["stripe_subscription_id"],
        unique=True,
    )

    # --- Founding member counter (singleton row, id=1) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS founding_member_count (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            count INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("INSERT INTO founding_member_count (id, count) VALUES (1, 0) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.drop_index("ix_workspace_stripe_subscription_id", table_name="workspace")
    op.drop_index("ix_workspace_stripe_customer_id", table_name="workspace")
    op.drop_column("workspace", "founding_member")
    op.drop_column("workspace", "stripe_price_id")
    op.drop_column("workspace", "stripe_subscription_status")
    op.drop_column("workspace", "stripe_subscription_id")
    op.drop_column("workspace", "stripe_customer_id")
    op.execute("DROP TABLE IF EXISTS founding_member_count")
