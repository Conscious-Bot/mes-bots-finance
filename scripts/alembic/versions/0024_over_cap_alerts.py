"""Pile 2.1 v2.c.5 : table over_cap_alerts (journal d'evenements over_cap).

Pourquoi une table dediee plutot que bias_events.status comme proxy de
prev_status (user 01/06 critique) : un candidat over_cap se resout a +30j ;
si la position est toujours over a ce moment, lire bias_events.open comme
prev_status retournerait 'dormant' et re-fire une nouvelle transition au
cycle suivant -- 'resolu-mais-toujours-over' devient indistinguable de
'jamais franchi'. C'est un compteur qui se re-arme tout seul.

Sementique stricte : 1 evenement = 1 franchissement = 1 prediction sur 1
contrefactuel (orthogonalite defendue depuis l'ADR 010). Si re-test roulant
souhaite plus tard = ajout delibere, pas defaut par construction.

Pattern miroir de kill_criteria_alerts (Sprint 15) : journal incremental
par evaluation. prev_status = last row status. Notify+wire SEULEMENT sur
transition dormant -> over (notified=1).

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-01
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE over_cap_alerts (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at               TEXT NOT NULL DEFAULT (datetime('now')),
            ticker                   TEXT NOT NULL,
            status                   TEXT NOT NULL
                                     CHECK(status IN ('over', 'dormant')),
            weight_pct               REAL NOT NULL,
            cap_pct                  REAL NOT NULL,
            conviction               INTEGER,
            notified                 INTEGER NOT NULL DEFAULT 0
                                     CHECK(notified IN (0, 1)),
            transition               TEXT
                                     CHECK(transition IN ('dormant_to_over',
                                                          'over_to_dormant',
                                                          'no_change')
                                           OR transition IS NULL),
            bias_event_id            INTEGER REFERENCES bias_events(id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_oca_ticker ON over_cap_alerts(ticker, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_oca_status ON over_cap_alerts(status, created_at)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_oca_status")
    op.execute("DROP INDEX IF EXISTS idx_oca_ticker")
    op.execute("DROP TABLE IF EXISTS over_cap_alerts")
