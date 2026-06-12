"""Ajoute colonnes consensus à stale_target_alerts (#134 enrichissement
cross-check consensus 12/06/2026).

Nouvelles colonnes (toutes nullables, pas de migration data) :
- consensus_target : float | NULL — target_mean yfinance.info en native ccy
- consensus_n : int | NULL — numberOfAnalystOpinions
- consensus_delta_pct : float | NULL — (target_olv / consensus_target - 1) * 100

Pourquoi nullable : `prices.get_analyst_consensus(ticker)` peut retourner None
(throttle, ticker non couvert). Le monitor doit dégrader gracefully sans
crasher (cf fail-closed L15).

Revision ID: 0057
Revises: 0056
"""
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stale_target_alerts ADD COLUMN consensus_target REAL")
    op.execute("ALTER TABLE stale_target_alerts ADD COLUMN consensus_n INTEGER")
    op.execute("ALTER TABLE stale_target_alerts ADD COLUMN consensus_delta_pct REAL")


def downgrade() -> None:
    # SQLite ne supporte pas DROP COLUMN natif <3.35. Pour rollback,
    # CREATE new table + copy + DROP + RENAME. Hors scope (downgrade rare).
    pass
