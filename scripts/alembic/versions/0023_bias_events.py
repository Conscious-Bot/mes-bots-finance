"""Pile 2.1 v1 mecanique : table bias_events (schema canonique user 31/05 close).

Structure SEULE. Aucune logique contrefactuel ici (cf docs/specs/
user_bias_detector_schema.md pour le complet). Le cron resolve_due_bias_events
existe en skeleton no-op : decouvrira les rows open, ne calculera rien
tant que la logique contrefactuel n'est pas implementee.

CHECK constraints sur les 4 enums canoniques (bias / action / status /
source). Si une valeur hors-enum est inseree -> IntegrityError immediate
(jamais de string libre silencieuse, cf user [[source-direct-fix]]).

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-31
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE bias_events (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at          TEXT NOT NULL,
            ticker              TEXT,
            bias                TEXT NOT NULL
                                CHECK(bias IN ('lock_in', 'fomo_greed', 'other')),
            action              TEXT NOT NULL
                                CHECK(action IN ('acted_on_bias', 'resisted')),
            decision_json       TEXT NOT NULL,
            counterfactual_json TEXT NOT NULL,
            resolution_json     TEXT,
            status              TEXT NOT NULL DEFAULT 'open'
                                CHECK(status IN ('open', 'resolved', 'void',
                                                 'thesis_invalidated',
                                                 'reentered', 'missing_data')),
            source              TEXT NOT NULL
                                CHECK(source IN ('auto_detected',
                                                 'telegram_tap', 'manual')),
            thesis_id           INTEGER REFERENCES theses(id),
            prediction_id       INTEGER REFERENCES predictions(id),
            note_tags_json      TEXT,
            horizon_days        INTEGER NOT NULL,
            resolve_at          TEXT NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX idx_bias_events_open ON bias_events(status, resolve_at)"
    )
    op.execute(
        "CREATE INDEX idx_bias_events_bias_action ON bias_events(bias, action, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_bias_events_ticker ON bias_events(ticker, created_at) "
        "WHERE ticker IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_bias_events_ticker")
    op.execute("DROP INDEX IF EXISTS idx_bias_events_bias_action")
    op.execute("DROP INDEX IF EXISTS idx_bias_events_open")
    op.execute("DROP TABLE IF EXISTS bias_events")
