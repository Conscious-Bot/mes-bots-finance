"""bot_preferences — Layer 3 : ce qui MARCHE pour CE user (mensuel).

Pendant agrege a Layer 2 : la ou bot_conceptions est une vue stable PAR
target, bot_preferences est une vue stable PAR PATTERN — calibree sur
outcomes (returns J+30, Brier, copilot_outcome_label).

Pourquoi separer de user_profile :
  - user_profile = "qui est l'user" (archetype, biais, tone)
  - bot_preferences = "ce qui a deterministically marche / pas marche
    pour cet user" (sizes, horizons, conviction levels, sectors)

Append-only, 1 snapshot par run (mensuel par defaut).

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bot_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("kind", sa.Text(), nullable=False),
        # kinds : conviction_calibration / sizing_outcome / horizon_outcome /
        # sector_outcome / bias_outcome / archetype_consistency
        sa.Column("snapshot_date", sa.Text(), nullable=False),
        sa.Column("metric_json", sa.Text(), nullable=False),  # raw numbers (samples, win rates, etc.)
        sa.Column("insight_text", sa.Text(), nullable=True),  # LLM synthesis 2-4 phrases
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),  # 0-100 calibre sur n
        sa.Column("n_samples", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="deterministic"),  # deterministic | llm_augmented
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_index("idx_pref_kind", "bot_preferences", ["kind"])
    op.create_index("idx_pref_date", "bot_preferences", ["snapshot_date"])


def downgrade():
    op.drop_index("idx_pref_date", "bot_preferences")
    op.drop_index("idx_pref_kind", "bot_preferences")
    op.drop_table("bot_preferences")
