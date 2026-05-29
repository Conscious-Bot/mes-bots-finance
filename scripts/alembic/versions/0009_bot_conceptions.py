"""bot_conceptions — vue stable du bot per ticker/sector/theme (Layer 2).

Pendant analytique de chat_extracted_signals : la ou ces derniers sont des
murmures bruts, bot_conceptions est la synthese digestee. Append-only,
versionnee, query last per (kind, target_key) pour avoir la vue courante.

Sources synthetisees (hierarchie) :
  inputs user (decisions reasoning) > theses > chat signals > interventions
  copilot > newsletter signals filtres ticker > Brier correctif.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bot_conceptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("kind", sa.Text(), nullable=False),  # ticker | sector | theme
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("conception_text", sa.Text(), nullable=False),
        sa.Column("conviction", sa.Integer(), nullable=False),  # 0-100
        sa.Column("valence", sa.Float(), nullable=True),  # -1 a +1
        sa.Column("sources_json", sa.Text(), nullable=True),  # {decisions:[], theses:[], signals:[], interventions:[]}
        sa.Column("n_signals_used", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
    )
    op.create_index("idx_conc_kind_target", "bot_conceptions", ["kind", "target_key"])
    op.create_index("idx_conc_created", "bot_conceptions", ["created_at"])


def downgrade():
    op.drop_index("idx_conc_created", "bot_conceptions")
    op.drop_index("idx_conc_kind_target", "bot_conceptions")
    op.drop_table("bot_conceptions")
