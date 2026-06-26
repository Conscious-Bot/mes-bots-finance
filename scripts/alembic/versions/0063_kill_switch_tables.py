"""kill_switch tables — disjoncteur grappe AI-compute (handoff spec 26/06/2026).

Deux tables pour la branche P1 (drawdown prix) du kill-condition :

(1) `cluster_value_snapshots` : daily snapshot de la valeur agrégée EUR
    de la grappe AI-compute. PK = snapshot_date (UPSERT-able pour idempotence).
    Sert au calcul du pic glissant 90j et du drawdown.

(2) `kill_triggers` : state machine des franchissements. Append-only via
    INSERT, UPDATE limité aux fields de résolution (status, override_*,
    resolved_at). Statuts : unresolved | executed | override_active |
    override_due | override_correct | override_failed | auto_execute_prescribed.

L'état d'épisode (anti-spam open/worst_stage/episode_id) vit dans le state
store JSON (storage.load_state / update_state), pas dans une table.

Cf vault doctrine "Kill-condition — disjoncteur de la grappe AI-compute" V3.
Cf [[manual-exec-must-create-cf]] pour le pattern monitor canonique.

Revision ID: 0063
Revises: 0062
"""
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # cluster_value_snapshots — daily snapshot grappe (PK = date, UPSERT-able)
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS cluster_value_snapshots (
            snapshot_date TEXT PRIMARY KEY,
            value_eur     REAL NOT NULL
        )
    """)

    # =========================================================================
    # kill_triggers — state machine 1-msg-par-franchissement
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS kill_triggers (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_type                TEXT NOT NULL,
            episode_id                  INTEGER NOT NULL DEFAULT 0,
            stage                       INTEGER NOT NULL CHECK(stage IN (1, 2, 3)),
            level_measured              REAL NOT NULL,
            prescribed_action           TEXT NOT NULL,
            status                      TEXT NOT NULL CHECK(status IN (
                                            'unresolved',
                                            'executed',
                                            'override_active',
                                            'override_due',
                                            'override_correct',
                                            'override_failed',
                                            'auto_execute_prescribed'
                                        )),
            created_at                  TEXT NOT NULL,
            override_text               TEXT,
            override_falsification_date TEXT,
            resolved_at                 TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_kill_triggers_status ON kill_triggers(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_kill_triggers_episode ON kill_triggers(episode_id)")

    # Append-only sur DELETE seulement ; UPDATE limité aux fields résolution
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS kill_triggers_no_delete
        BEFORE DELETE ON kill_triggers
        BEGIN SELECT RAISE(ABORT, 'kill_triggers : pas de DELETE'); END
    """)
    # Empêche modification des fields immuables (trigger_type, stage, level_measured,
    # prescribed_action, created_at). Permet modification status + override_* + resolved_at.
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS kill_triggers_no_update_anchors
        BEFORE UPDATE ON kill_triggers
        FOR EACH ROW
        WHEN
            OLD.trigger_type != NEW.trigger_type
         OR OLD.stage != NEW.stage
         OR OLD.level_measured != NEW.level_measured
         OR OLD.prescribed_action != NEW.prescribed_action
         OR OLD.created_at != NEW.created_at
         OR OLD.episode_id != NEW.episode_id
        BEGIN
            SELECT RAISE(ABORT, 'kill_triggers : anchors immuables (trigger_type/stage/level/action/created_at/episode_id)');
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS kill_triggers_no_update_anchors")
    op.execute("DROP TRIGGER IF EXISTS kill_triggers_no_delete")
    op.execute("DROP INDEX IF EXISTS idx_kill_triggers_episode")
    op.execute("DROP INDEX IF EXISTS idx_kill_triggers_status")
    op.execute("DROP TABLE IF EXISTS kill_triggers")
    op.execute("DROP TABLE IF EXISTS cluster_value_snapshots")
