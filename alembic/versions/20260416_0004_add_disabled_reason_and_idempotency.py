"""Add disabled_reason to api_keys and idempotency index on balance_transactions.

Revision ID: 20260416_0004
Revises: 20260414_0003
Create Date: 2026-04-16 10:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260416_0004"
down_revision = "20260414_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Task #4: disabled_reason column for api_keys
    op.add_column("api_keys", sa.Column("disabled_reason", sa.String(length=64), nullable=True))

    # Task #3: unique index on (note) for topup transactions to enforce idempotency
    # Partial unique index: only enforce uniqueness where note IS NOT NULL
    # and transaction_type = 'topup'
    op.create_index(
        "ix_balance_transactions_topup_note_unique",
        "balance_transactions",
        ["note"],
        unique=True,
        postgresql_where=sa.text("note IS NOT NULL AND transaction_type = 'topup'"),
    )


def downgrade() -> None:
    op.drop_index("ix_balance_transactions_topup_note_unique", table_name="balance_transactions")
    op.drop_column("api_keys", "disabled_reason")
