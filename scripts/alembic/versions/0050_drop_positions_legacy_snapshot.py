"""DROP positions_legacy_snapshot — confiance VUE atteinte.

Cf clôture session 09/06 : 'positions_legacy_snapshot conservée pour rollback
runtime si la VUE casse. Drop après quelques jours de confiance.'

Confiance acquise (vérifié 09/06) :
  - 1690 tests verts depuis 0048
  - 5 consumers SQL-direct migrés vers BookLine (#127d)
  - VUE NULL fail-closed L15 + helper rolling = single source canonique
  - PMP fiscal FR correct sur les 8 re-buy tickers
  - Aucun caller `positions_legacy_snapshot` dans le code prod (grep clean)

Aucun consumer du snapshot dans le code prod. C'est un artefact transitoire
de la stratégie réversible de 0048. Le drop libère ~30 rows + indices liés.

DOWNGRADE asymétrique : ne ressuscite PAS le snapshot (perdu à jamais).
Re-créer une table vide avec le schéma originel pour permettre un éventuel
`alembic downgrade` théorique, mais sans data. Le snapshot a vécu son rôle.

Backup avant migration :
  cp data/bot.db data/bot.db.backup_pre_0050_<date>
"""
from __future__ import annotations

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS positions_legacy_snapshot")


def downgrade() -> None:
    # Re-création schéma sans data (snapshot perdu à jamais).
    op.execute("""
        CREATE TABLE positions_legacy_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            qty REAL,
            avg_cost REAL,
            realized_pnl REAL,
            opened_at TEXT,
            last_updated TEXT,
            notes TEXT,
            status TEXT,
            account TEXT,
            wrapper TEXT,
            last_price_native REAL,
            last_price_currency TEXT,
            price_asof TEXT,
            price_source TEXT,
            fx_rate_to_eur REAL,
            fx_asof TEXT,
            fx_source TEXT,
            avg_cost_eur REAL,
            avg_cost_native REAL,
            avg_cost_currency TEXT,
            fx_at_purchase REAL,
            last_price_eur REAL,
            avg_cost_value REAL,
            avg_cost_asof TEXT
        )
    """)
