"""Add billing, pricing, and admin balance fields.

Revision ID: 20260409_0002
Revises: 20260409_0001
Create Date: 2026-04-09 16:35:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260409_0002"
down_revision = "20260409_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "users",
        sa.Column("balance", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
    )
    op.alter_column("users", "is_admin", server_default=None)
    op.alter_column("users", "balance", server_default=None)

    op.add_column(
        "usage_logs",
        sa.Column("billed_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "usage_logs",
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
    )
    op.alter_column("usage_logs", "billed_amount", server_default=None)
    op.alter_column("usage_logs", "currency", server_default=None)

    op.create_table(
        "model_pricings",
        sa.Column("provider_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("input_cost_per_1k_tokens", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("output_cost_per_1k_tokens", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "model_name", name="uq_model_pricings_provider_model"),
    )

    op.create_table(
        "balance_transactions",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("api_key_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("usage_log_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("transaction_type", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("margin_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usage_log_id"], ["usage_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("balance_transactions")
    op.drop_table("model_pricings")
    op.drop_column("usage_logs", "currency")
    op.drop_column("usage_logs", "billed_amount")
    op.drop_column("users", "balance")
    op.drop_column("users", "is_admin")
