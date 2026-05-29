"""ticker_axes — tagging per ticker sur 3 axes pour redefinir redondance.

Per critique #1 review : "Redondance != meme theme. Il faut la definir par
driver partage + substituabilite, pas par secteur. Concrétement, tagger
chaque ligne sur trois axes — driver de demande, etage de la chaine de
valeur, source de moat — et ne declarer 'doublon' que si driver ET etage
coincident."

Plus un 4eme axe pour la decorrelation : macro_factor (capex IA, taux,
defense, commodities, ...) pour separer 'unicite interne' de 'decorrelation
au facteur dominant'.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticker_axes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("demand_driver", sa.Text(), nullable=False),
        # ex: "AI capex hyperscalers" / "Memory cycle DRAM/HBM" / "Defense rearmament EU"
        sa.Column("value_chain_stage", sa.Text(), nullable=False),
        # ex: "fabless designer" / "pure foundry" / "equipment maker" / "wafer supplier" / "operator"
        sa.Column("moat_source", sa.Text(), nullable=False),
        # ex: "monopoly EUV" / "duopoly HBM" / "switching cost EDA" / "brand+aftermarket annuity"
        sa.Column("macro_factor", sa.Text(), nullable=False),
        # ex: "AI capex" / "rates" / "energy commodities" / "rare earths" / "defense rearmament"
        sa.Column("alt_drivers_json", sa.Text(), nullable=True),
        # JSON list of secondary drivers if the ticker plays multiple stories
        sa.Column("confidence", sa.Integer(), nullable=True),  # 0-100
        sa.Column("rationale", sa.Text(), nullable=True),  # 1-2 sentences why
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_index("idx_axes_ticker", "ticker_axes", ["ticker"])
    op.create_index("idx_axes_macro", "ticker_axes", ["macro_factor"])


def downgrade():
    op.drop_index("idx_axes_macro", "ticker_axes")
    op.drop_index("idx_axes_ticker", "ticker_axes")
    op.drop_table("ticker_axes")
