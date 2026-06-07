"""Phase 1.5 stage 2 : table risk_signal_evaluations (live state cron-written).

Pattern miroir de macro_regime_alerts (0029) : journal append-only.
1 row = 1 evaluation cron d'un (risk_id, signal_id). On lit la derniere
row pour "current_status" via SELECT ... ORDER BY evaluated_at DESC LIMIT 1.

Doctrine L17 LESSONS : declarative en YAML versionne (config/risk_watch.yaml),
live state en DB append-only (cette table). Plus de write-back mecanique sur
le YAML/JSON par le cron.

Avant cette migration : intelligence/risk_signal_monitor.py muait
scripts/risk_watch.json (current_status, last_evaluated_at, last_eval_reason,
last_eval_confidence, last_eval_evidence_ids). Apres : append-only en DB.

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-07
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE risk_signal_evaluations (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluated_at        TEXT NOT NULL DEFAULT (datetime('now')),
            risk_id             TEXT NOT NULL,
            signal_id           TEXT NOT NULL,
            status              TEXT NOT NULL
                                CHECK(status IN ('monitoring', 'at_risk',
                                                 'triggered', 'resolved')),
            reason              TEXT,
            confidence          INTEGER
                                CHECK(confidence IS NULL OR
                                      (confidence >= 0 AND confidence <= 100)),
            evidence_ids_json   TEXT,
            transition          TEXT
                                CHECK(transition IN ('no_change', 'changed')
                                      OR transition IS NULL)
        )
    """)
    # Index principal : "latest evaluation per (risk_id, signal_id)" query
    # via ORDER BY evaluated_at DESC LIMIT 1 sur composite key.
    op.execute(
        "CREATE INDEX idx_rse_risk_signal ON "
        "risk_signal_evaluations(risk_id, signal_id, evaluated_at DESC)"
    )
    # Index timeline pour audit + cleanup futur
    op.execute(
        "CREATE INDEX idx_rse_evaluated ON risk_signal_evaluations(evaluated_at)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_rse_evaluated")
    op.execute("DROP INDEX IF EXISTS idx_rse_risk_signal")
    op.execute("DROP TABLE IF EXISTS risk_signal_evaluations")
