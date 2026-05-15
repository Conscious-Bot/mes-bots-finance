"""portfolio_targets table + positions.account column

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "positions",
        sa.Column("account", sa.Text(), nullable=False, server_default="TR"),
    )

    op.create_table(
        "portfolio_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=True),
        sa.Column("target_eur", sa.Float(), nullable=False),
        sa.Column("target_weight_pct", sa.Float(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="planned"),
        sa.Column("phase_week", sa.Integer(), nullable=True),
        sa.Column("active_from", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("active_to", sa.Text(), nullable=True),
        sa.Column("source_doc", sa.Text(), nullable=True),
        sa.Column("thesis_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["thesis_id"], ["theses.id"]),
    )
    op.create_index("idx_targets_ticker", "portfolio_targets", ["ticker"])
    op.create_index("idx_targets_account", "portfolio_targets", ["account"])
    op.create_index("idx_targets_status", "portfolio_targets", ["status"])


def downgrade():
    op.drop_index("idx_targets_status", "portfolio_targets")
    op.drop_index("idx_targets_account", "portfolio_targets")
    op.drop_index("idx_targets_ticker", "portfolio_targets")
    op.drop_table("portfolio_targets")
    # SQLite drop_column requires table rebuild; skipped for compat
