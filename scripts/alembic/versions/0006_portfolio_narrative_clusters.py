"""portfolio_narrative_clusters — Sprint 6, LLM narrative groupings

Hebdo (cron). Stocke clusters narratifs identifies par Opus + edge_positions
+ redundant_positions. Le grade deterministe consomme le snapshot le plus
recent pour raffiner T2_redondant et decorrelation_star.

Append-only : 1 snapshot par run. Re-execution = nouvelle ligne.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_narrative_clusters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("snapshot_date", sa.Text(), nullable=False),
        sa.Column("clusters_json", sa.Text(), nullable=False),
        sa.Column("edges_json", sa.Text(), nullable=False),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_narrative_cluster_date", "portfolio_narrative_clusters", ["snapshot_date"]
    )


def downgrade():
    op.drop_index("idx_narrative_cluster_date", "portfolio_narrative_clusters")
    op.drop_table("portfolio_narrative_clusters")
