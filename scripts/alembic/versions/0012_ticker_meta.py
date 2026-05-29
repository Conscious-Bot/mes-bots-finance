"""ticker_meta — extension Sprint 14 : fade-rate + upstream deps + valo overlay.

Per critique :
  - "Cartographier les points de defaillance uniques de la chaine. Ta vraie
    concentration n'est pas dans le book, elle est en amont : TSMC fabrique
    pour AMD, Broadcom, Astera. Un incident TSMC touche bien plus que la
    ligne TSMC. HBM = 3 fournisseurs, EUV = ASML seul."

  - "Operationnaliser ton cadre Mauboussin. Encode le fade-rate par nom en
    une courbe de poids-cible : fade quasi-nul (ASML/TSMC/SNPS) -> poids
    cible eleve ; fade eleve (Lasertec, memoire au pic) -> poids cible bas.
    Le 'sizing conviction' devient alors l'ecart entre poids reel et
    poids-implicite-par-le-fade — rigoureux, pas un nombre magique."

  - "Ajoute un overlay valo/attentes (reverse-DCF 'qu'est-ce qui est
    price-in ?') pour flagger quand les attentes depassent meme le bull case
    (AMD ~92x, memoire au pic)."

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticker_meta",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("ticker", sa.Text(), nullable=False),
        # Mauboussin : 0=infinite annuity (Coca, ASML), 100=immediate revert (Lasertec, peak memory)
        sa.Column("fade_rate_score", sa.Integer(), nullable=False),
        # Years of moat durability (rough)
        sa.Column("moat_durability_years", sa.Integer(), nullable=True),
        # Upstream deps: list of {"node": "TSMC N3", "share_of_revenue_or_capacity": 0.X}
        sa.Column("upstream_critical_deps_json", sa.Text(), nullable=True),
        # What's priced in (1 short sentence per critique reverse-DCF)
        sa.Column("valo_what_priced_in", sa.Text(), nullable=True),
        sa.Column("valo_pe_or_proxy", sa.Float(), nullable=True),
        # Whether expectations exceed bull case
        sa.Column("valo_above_bull_case", sa.Boolean(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_index("idx_meta_ticker", "ticker_meta", ["ticker"])
    op.create_index("idx_meta_fade", "ticker_meta", ["fade_rate_score"])


def downgrade():
    op.drop_index("idx_meta_fade", "ticker_meta")
    op.drop_index("idx_meta_ticker", "ticker_meta")
    op.drop_table("ticker_meta")
