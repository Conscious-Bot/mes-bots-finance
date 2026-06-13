"""group_cap monitor (#149) : journal append-only des transitions dormant/over
par GROUPE de tickers (vs over_cap qui est par-position).

Pattern canonique cf docs/templates/monitor_pattern.md (4e monitor apres
kill_criteria + over_cap + stale_target). Mission : flagger si l'exposition
aggregee d'un GROUPE de tickers (e.g. memory makers Hynix + Micron) depasse
le cap declaré. Premier groupe live : memory = {000660.KS, MU} cap 6%
(decision Olivier 13/06 post Hynix repose Regime A).

Status enum :
  dormant : group_pct <= cap_pct (sous le cap, OK)
  over    : group_pct > cap_pct (au-dessus du cap, action recommandee)

Transition actionable : dormant_to_over -> notify Telegram + audit row.
Transition observable : over_to_dormant -> audit seulement.

PAS de wire bias_events (signal pur de gouvernance taille groupe,
pas anti-biais comportemental individual).

Revision ID: 0059
Revises: 0058
"""
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE group_cap_alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            group_key    TEXT NOT NULL,
            tickers_json TEXT NOT NULL,
            status       TEXT NOT NULL CHECK(status IN ('dormant', 'over')),
            group_pct    REAL NOT NULL,
            cap_pct      REAL NOT NULL,
            group_eur    REAL NOT NULL,
            book_eur     REAL NOT NULL,
            notified     INTEGER NOT NULL DEFAULT 0,
            transition   TEXT CHECK(transition IN (
                'no_change', 'dormant_to_over', 'over_to_dormant'
            ))
        )
    """)
    op.execute(
        "CREATE INDEX idx_group_cap_key ON group_cap_alerts(group_key, created_at)",
    )
    op.execute(
        "CREATE INDEX idx_group_cap_status "
        "ON group_cap_alerts(status, created_at)",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_group_cap_status")
    op.execute("DROP INDEX IF EXISTS idx_group_cap_key")
    op.execute("DROP TABLE IF EXISTS group_cap_alerts")
