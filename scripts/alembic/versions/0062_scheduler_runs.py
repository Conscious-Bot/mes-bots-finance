"""scheduler_runs : journal append-only des fires APScheduler (audit 14/06/2026).

Sert :
- Cron observability : last fire timestamp per job (skill /system-health)
- Catch silent-dead crons (job qui a stop sans alerte)
- Forensics : si un signal manque, voir si le cron a tourne ou pas
- Cost tracking : duration_s en aggregation pour identifier crons lents

Append-only strict (no DELETE / no UPDATE post-insert). Pattern identique
research_brief_log (0061) et predictions/bias_events/alerts (0058).

CREATE TABLE ONLY -- pas de recreate sur table existante, donc pas besoin
des 3 gardes "migration sur table sous cron". Safe a appliquer hot.

Revision ID: 0062
Revises: 0061
"""
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE scheduler_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name     TEXT NOT NULL,
            started_at   TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at     TEXT,
            status       TEXT NOT NULL DEFAULT 'started'
                         CHECK(status IN ('started', 'success', 'fail')),
            duration_s   REAL,
            error_msg    TEXT
        )
    """)
    op.execute(
        "CREATE INDEX idx_scheduler_runs_job_time "
        "ON scheduler_runs(job_name, started_at)"
    )
    op.execute(
        "CREATE INDEX idx_scheduler_runs_status "
        "ON scheduler_runs(status, started_at)"
    )
    op.execute("""
        CREATE TRIGGER scheduler_runs_no_delete
        BEFORE DELETE ON scheduler_runs
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'scheduler_runs is append-only (audit 14/06/2026). DELETE interdit.');
        END
    """)
    # NOTE : pas de no_update trigger global car on UPDATE ended_at/status/duration
    # sur la meme row en fin de job (started -> success/fail). Update legitime.
    # Garde colonne started_at + id immuables via no_update_immutable trigger :
    op.execute("""
        CREATE TRIGGER scheduler_runs_no_update_immutable
        BEFORE UPDATE ON scheduler_runs
        FOR EACH ROW
        WHEN (NEW.id != OLD.id OR NEW.job_name != OLD.job_name
              OR NEW.started_at != OLD.started_at)
        BEGIN
            SELECT RAISE(ABORT, 'scheduler_runs : id/job_name/started_at immuables (append-only).');
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS scheduler_runs_no_update_immutable")
    op.execute("DROP TRIGGER IF EXISTS scheduler_runs_no_delete")
    op.execute("DROP INDEX IF EXISTS idx_scheduler_runs_status")
    op.execute("DROP INDEX IF EXISTS idx_scheduler_runs_job_time")
    op.execute("DROP TABLE IF EXISTS scheduler_runs")
