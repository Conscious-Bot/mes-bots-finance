"""data_clusters_snapshots — Sprint 17 cache du run hebdo de clustering.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_clusters_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("snapshot_date", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
    )
    op.create_index("idx_dc_date", "data_clusters_snapshots", ["snapshot_date"])


def downgrade():
    op.drop_index("idx_dc_date", "data_clusters_snapshots")
    op.drop_table("data_clusters_snapshots")
