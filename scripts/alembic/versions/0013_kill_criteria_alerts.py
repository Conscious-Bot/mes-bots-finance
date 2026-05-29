"""kill_criteria_alerts — Sprint 15 : monitor des invalidation_triggers per thesis.

Per la critique : "Alerte si un kill-criterion se declenche."

Pour chaque these active, on evalue ses invalidation_triggers contre l'etat
actuel (prix, age, signaux recents, P&L). Status = dormant / at_risk /
triggered. Append-only. Telegram alert sur transition X → triggered.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kill_criteria_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("thesis_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),  # dormant | at_risk | triggered
        sa.Column("triggers_evaluated_json", sa.Text(), nullable=False),  # list of {trigger, status, reason}
        sa.Column("dominant_reason", sa.Text(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),  # current state quoted
        sa.Column("confidence", sa.Integer(), nullable=True),  # 0-100
        sa.Column("notified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_index("idx_kca_thesis", "kill_criteria_alerts", ["thesis_id"])
    op.create_index("idx_kca_status", "kill_criteria_alerts", ["status"])
    op.create_index("idx_kca_ticker", "kill_criteria_alerts", ["ticker"])


def downgrade():
    op.drop_index("idx_kca_ticker", "kill_criteria_alerts")
    op.drop_index("idx_kca_status", "kill_criteria_alerts")
    op.drop_index("idx_kca_thesis", "kill_criteria_alerts")
    op.drop_table("kill_criteria_alerts")
