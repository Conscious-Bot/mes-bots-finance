"""positions M1 typed columns : last_price_native + price_asof + fx_asof + fx_rate_to_eur.

Spec QUALITY_BAR Axe 3 1er geste FONDATIONNEL : "tuer la denormalisation
eur_value/notes, colonnes typees + 1 job de reconciliation unique via
prices.get(). Tout lit cet etat ; il est casse aujourd'hui."

M1 doctrine : tout datum est un triple (valeur, asof, source). Sur positions
on cache le LATEST (denormalisation explicite pour fast read), pas le
DERIVE (eur_value reste calculee live via shared.valuation.position_valuation).

Colonnes ajoutees :
- last_price_native (REAL) : dernier prix observe en devise native
- last_price_currency (TEXT) : devise du prix
- price_asof (TEXT) : timestamp ISO observation prix
- price_source (TEXT) : source ('yfinance', 'manual', ...)
- fx_rate_to_eur (REAL) : taux FX vers EUR au moment de price_asof
- fx_asof (TEXT) : timestamp ISO observation FX
- fx_source (TEXT) : source FX

Note critique : on n'ajoute PAS market_value_eur / eur_value comme colonne.
Le test test_positions_schema_has_no_eur_value_column verrouille ca.
La valeur EUR est derivee live dans shared/valuation.py.

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-07
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    # Cache LATEST observations on positions row (denormalisation pour fast read).
    # SOURCE DE VERITE reste price_history / fx_history append-only.
    # Reconciliation job copie latest -> these columns.
    op.execute("ALTER TABLE positions ADD COLUMN last_price_native REAL")
    op.execute("ALTER TABLE positions ADD COLUMN last_price_currency TEXT")
    op.execute("ALTER TABLE positions ADD COLUMN price_asof TEXT")
    op.execute("ALTER TABLE positions ADD COLUMN price_source TEXT")
    op.execute("ALTER TABLE positions ADD COLUMN fx_rate_to_eur REAL")
    op.execute("ALTER TABLE positions ADD COLUMN fx_asof TEXT")
    op.execute("ALTER TABLE positions ADD COLUMN fx_source TEXT")


def downgrade():
    # SQLite < 3.35 ne supporte pas DROP COLUMN nativement -- non-reversible accepte
    pass
