"""portfolio_grades — daily snapshot of overall portfolio quality grade

Append-only history. Each row = 1 day. Allows trend tracking + before/after
simulation (compare 2 snapshots before/after a hypothetical trade).

Used by :
- Dashboard panel "Note PF" (latest snapshot)
- Trend computation (Δ vs 7j ago)
- Copilot brief (mentions delta if trade simulated)
- Future auto-rebalancing : proposes trades that improve the grade

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_grades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("snapshot_date", sa.Text(), nullable=False),  # YYYY-MM-DD pour query
        sa.Column("overall_score", sa.Integer(), nullable=False),  # 0-100
        sa.Column("overall_grade", sa.Text(), nullable=False),  # A+ / A / A- / B+ / ... / D
        sa.Column("dimensions_json", sa.Text(), nullable=False),  # full breakdown
        sa.Column("total_capital_eur", sa.Float(), nullable=True),
        sa.Column("n_positions", sa.Integer(), nullable=True),
        sa.Column("n_theses_active", sa.Integer(), nullable=True),
        sa.Column("computation_version", sa.Text(), nullable=False, server_default="sprint5_deterministic"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("idx_grade_date", "portfolio_grades", ["snapshot_date"])
    op.create_index("idx_grade_snapshot_at", "portfolio_grades", ["snapshot_at"])


def downgrade():
    op.drop_index("idx_grade_snapshot_at", "portfolio_grades")
    op.drop_index("idx_grade_date", "portfolio_grades")
    op.drop_table("portfolio_grades")
