"""research_brief_log : journal append-only des briefs /research (spec #152).

Sert :
- Rate-limit (1 brief / heure / user)
- Budget LLM tracking (cost_actual_usd cumulé / jour pour hard-stop)
- Audit historique (corpus utile future Unit C narrative_drift si barrière #150
  lève un jour — training data sur la prose d'Olivier calibrée)

Append-only strict (no DELETE / no UPDATE post-insert). Cohérent avec
predictions / bias_events / monitor alerts patterns 0058.

CREATE TABLE ONLY — pas de recreate-table sur table existante, donc pas
besoin des 3 gardes "migration sur table sous cron" (bot-stop + count-assert
+ CHECK SQL). Migration safe à appliquer hot sans stop bot.

Revision ID: 0061
Revises: 0060
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE research_brief_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            user_id         TEXT NOT NULL,
            target          TEXT NOT NULL,
            target_type     TEXT NOT NULL
                            CHECK(target_type IN ('ticker', 'theme')),
            success         INTEGER NOT NULL DEFAULT 0
                            CHECK(success IN (0, 1)),
            cost_actual_usd REAL,
            error_reason    TEXT,
            response_chars  INTEGER
        )
    """)
    op.execute(
        "CREATE INDEX idx_research_brief_user_time "
        "ON research_brief_log(user_id, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_research_brief_target "
        "ON research_brief_log(target, created_at)"
    )
    op.execute("""
        CREATE TRIGGER research_brief_log_no_delete
        BEFORE DELETE ON research_brief_log
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'research_brief_log is append-only (spec #152). DELETE interdit.');
        END
    """)
    op.execute("""
        CREATE TRIGGER research_brief_log_no_update
        BEFORE UPDATE ON research_brief_log
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'research_brief_log is append-only (spec #152). UPDATE interdit.');
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS research_brief_log_no_update")
    op.execute("DROP TRIGGER IF EXISTS research_brief_log_no_delete")
    op.execute("DROP INDEX IF EXISTS idx_research_brief_target")
    op.execute("DROP INDEX IF EXISTS idx_research_brief_user_time")
    op.execute("DROP TABLE IF EXISTS research_brief_log")
