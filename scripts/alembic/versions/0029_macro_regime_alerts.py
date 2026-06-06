"""Phase A macro stress monitor : table macro_regime_alerts (journal regime).

Pattern miroir de over_cap_alerts (0024) : journal d'evenements append-only.
1 row = 1 evaluation du regime macro. transition = 'changed' quand le label
diffère du précédent, 'no_change' sinon.

Pas de bias_event_id (macro regime != bias portfolio). Le panneau lit la
derniere row pour afficher le regime courant ; les transitions futures
notifient via Telegram.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-06
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE macro_regime_alerts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            regime        TEXT NOT NULL
                          CHECK(regime IN ('COMPLACENT', 'RISK_ON',
                                           'LATE_CYCLE', 'FRAGILE', 'STRESS')),
            score         REAL NOT NULL,
            danger_count  INTEGER NOT NULL,
            warn_count    INTEGER NOT NULL,
            asleep_count  INTEGER NOT NULL,
            silent_count  INTEGER NOT NULL,
            triggers      TEXT NOT NULL,
            notified      INTEGER NOT NULL DEFAULT 0
                          CHECK(notified IN (0, 1)),
            transition    TEXT
                          CHECK(transition IN ('no_change', 'changed')
                                OR transition IS NULL)
        )
    """)
    op.execute(
        "CREATE INDEX idx_mra_created ON macro_regime_alerts(created_at)"
    )
    op.execute(
        "CREATE INDEX idx_mra_regime ON macro_regime_alerts(regime, created_at)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mra_regime")
    op.execute("DROP INDEX IF EXISTS idx_mra_created")
    op.execute("DROP TABLE IF EXISTS macro_regime_alerts")
