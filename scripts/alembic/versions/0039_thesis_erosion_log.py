"""thesis_erosion_log : journal append-only erosion contenu these vs evidence post-entry.

Aiguillage anti-entetement complementaire (non redondant) :
- thesis_track_record : Brier empirique (predictions).
- M14 thesis_health_metrics : staleness temporelle (last_reviewed age).
- ICI : erosion de CONTENU au niveau driver -- l'evidence depuis opened_at
  contredit-elle les key_drivers / declenche-t-elle invalidation_triggers ?

Pattern monitor adapte : append-only, verdict cron-compute (pas de transition
ok->breach comme stress-gate ; chaque run = un snapshot verdict). 5 verdicts :
- INTACT : drivers confirmes/neutres
- EROSION_DETECTED : au moins un driver erode (net <= -1.5)
- INVALIDATION_HIT : >=1 invalidation_trigger declenche par evidence
- STALE_UNUPDATED : 0 signal materiel depuis opened_at + ago > 45j (angle mort)
- REVIEW_DUE_DEGRADED : LLM down sur majorite signals -> L15 fail-closed

Coute LLM Haiku par signal (top N par materialite plafond _TOP_N=12).

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-07
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE thesis_erosion_log (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            computed_at              TEXT NOT NULL DEFAULT (datetime('now')),
            thesis_id                INTEGER NOT NULL REFERENCES theses(id),
            ticker                   TEXT NOT NULL,
            verdict                  TEXT NOT NULL CHECK(verdict IN (
                'INTACT', 'EROSION_DETECTED', 'INVALIDATION_HIT',
                'STALE_UNUPDATED', 'REVIEW_DUE_DEGRADED'
            )),
            n_confirm                INTEGER NOT NULL DEFAULT 0,
            n_erode                  INTEGER NOT NULL DEFAULT 0,
            n_invalidation_hit       INTEGER NOT NULL DEFAULT 0,
            driver_status_json       TEXT NOT NULL DEFAULT '[]',
            signals_considered_json  TEXT NOT NULL DEFAULT '[]',
            degraded                 INTEGER NOT NULL DEFAULT 0,
            steer                    TEXT
        )
    """)
    op.execute("""
        CREATE INDEX idx_erosion_thesis ON thesis_erosion_log(thesis_id, computed_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_erosion_verdict ON thesis_erosion_log(verdict, computed_at DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS thesis_erosion_log")
