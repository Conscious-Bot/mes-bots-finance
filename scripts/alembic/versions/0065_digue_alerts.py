"""digue_alerts — journal des digues de concentration ADR 015.

Table journal append-only du système de digues sur drawdown RÉALISÉ du book
(equity vs high-water-mark, cf ADR 015 §3). Signal = portfolio_snapshots.
drawdown_pct, JAMAIS classify_regime (capteur à faux positifs).

États gradués (réconcilie le "un seul gel gradué" d'ADR 015 §3 digue 2) :
  - normal     : DD > -15%
  - gel_15     : -15% >= DD > -25%  (Digue 1 — gèle /position_buy, ne vend rien)
  - gel_25     : -25% >= DD > -35%  (vigilance renforcée, MÊME action gel)
  - prorata_35 : DD <= -35%         (Digue 2 — prorata 20% compute_ai, gel maintenu)

Append-only strict (pattern monitor canonique, cf docs/templates/monitor_pattern.md).
JAMAIS de DELETE applicatif. created_at DEFAULT (cure MODE B).

Revision ID: 0065
Revises: 0064
"""
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS digue_alerts (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            drawdown_pct      REAL NOT NULL,
            hwm_value_eur     REAL,
            current_value_eur REAL,
            snapshot_date     TEXT,
            status            TEXT NOT NULL
                              CHECK(status IN ('normal','gel_15','gel_25','prorata_35')),
            notified          INTEGER NOT NULL DEFAULT 0,
            transition        TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_digue_created ON digue_alerts(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_digue_status ON digue_alerts(status, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS digue_alerts")
