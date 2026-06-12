"""stale_target monitor (#134) : journal append-only des transitions
alive/dying/dead par these active.

Pattern canonique cf docs/templates/monitor_pattern.md (3e monitor apres
kca + over_cap). Detection des targets perimees vs cost roulant : un
target pose avant rally peut etre rattrape (cost depasse) ou la marge
peut devenir minime. Surface le signal SANS auto-recompute target
(humain decide -- cf L30 anti-piege "cible figee + cost roulant").

Status enum :
  alive  : (target - cost) / cost >= seuil_edge (marge confortable)
  dying  : 0 <= (target - cost) / cost < seuil_edge (marge mince)
  dead   : cost >= target (target rattrape ou depasse)

Transition actionable : alive->dying et dying->dead -> notify Telegram.
PAS de wire bias_event (signal pur, pas anti-bias mecanique).

Revision ID: 0056_stale_target_alerts
Revises: 0055_append_only_triggers
Create Date: 2026-06-12
"""
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE stale_target_alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            thesis_id    INTEGER NOT NULL,
            ticker       TEXT NOT NULL,
            status       TEXT NOT NULL CHECK(status IN ('alive', 'dying', 'dead')),
            cost_eur     REAL NOT NULL,
            target_eur   REAL NOT NULL,
            edge_pct     REAL NOT NULL,
            notified     INTEGER NOT NULL DEFAULT 0,
            transition   TEXT CHECK(transition IN (
                'no_change', 'alive_to_dying', 'dying_to_dead',
                'dying_to_alive', 'dead_to_dying', 'dead_to_alive',
                'alive_to_dead'
            ))
        )
    """)
    op.execute(
        "CREATE INDEX idx_stale_target_thesis_id "
        "ON stale_target_alerts(thesis_id, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_stale_target_status "
        "ON stale_target_alerts(status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stale_target_status")
    op.execute("DROP INDEX IF EXISTS idx_stale_target_thesis_id")
    op.execute("DROP TABLE IF EXISTS stale_target_alerts")
