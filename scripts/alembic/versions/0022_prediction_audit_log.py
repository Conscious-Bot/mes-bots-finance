"""PIT bitemporal pour predictions (ADR-001) : prediction_audit_log append-only.

Strategie user 31/05/2026 point #4 (saved-PIT) : "value at time T auditable
-- pour qu'un pro puisse auditer, pas juste voir l'instant present".

L'ADR-001 listait `predictions.brier_score` comme "deja append-only via
resolved_at", mais ce n'est vrai que pour la PREMIERE resolution. Quand on
UPDATE l'outcome apres coup (cas concret 31/05 : re-resolve NVDA 50, AVGO 51,
MSFT 53 apres fix get_close_on), l'ancien outcome est OVERWRITE silencieusement.
Sans history, la recalib_map fittee post-fix ne sait pas que NVDA etait
"neutral" avant -- elle apprend du resultat final, pas du chemin.

Solution : `prediction_audit_log` append-only au pattern `position_audit_log`.
Toute mutation de (resolved_at, final_price, return_pct, outcome,
credibility_delta, brier_score) y ecrit une ligne avec payload_json full
snapshot + event_type ('resolve' premiere fois | 're_resolve_pre' + 're_resolve'
si overwrite).

Wrap dans shared/storage.resolve_prediction_row (meme commit que cette
migration) lit l'etat existant avant UPDATE, log dans audit_log si necessaire,
puis applique l'UPDATE.

Backfill : separe (scripts/backfill_predictions_audit_20260531.py) ramene
les 3 mutations du 31/05 depuis data/bot.db.backup_pre_resolve_fix_*.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-31
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS prediction_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id INTEGER NOT NULL REFERENCES predictions(id),
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
            payload_json TEXT NOT NULL DEFAULT '{}',
            source TEXT,
            actor TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pred_audit_pid "
        "ON prediction_audit_log(prediction_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pred_audit_type "
        "ON prediction_audit_log(event_type, occurred_at)"
    )
    # Trigger append-only : aucun UPDATE accepte (pattern identique a
    # position_audit_log_no_update).
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS prediction_audit_log_no_update
        BEFORE UPDATE ON prediction_audit_log
        BEGIN
            SELECT RAISE(ABORT, 'prediction_audit_log is append-only -- INSERT seulement');
        END
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS prediction_audit_log_no_update")
    op.execute("DROP INDEX IF EXISTS idx_pred_audit_pid")
    op.execute("DROP INDEX IF EXISTS idx_pred_audit_type")
    op.execute("DROP TABLE IF EXISTS prediction_audit_log")
