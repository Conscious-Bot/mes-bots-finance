"""#2 Friction décision : table position_decisions_context.

Snapshot canonique du contexte au moment de chaque /trade confirm. Permet
post-mortem auto +30j/+90j pour mesurer si décision était alignée avec
système ou contre, et si l'outcome a validé qui ?

Doctrine : nourrir le bias_ledger en DONNEES per-decision concretes.
Avant : bias_ledger aggrege manuel + sample test. Apres : chaque trade
contribue une row contextuelle resolved.

Verdict categories (rempli par cron retrospective +30j/+90j) :
 - aligned_positive : decision alignee systeme + outcome positif
 - aligned_negative : alignee + outcome negatif (signal failed)
 - against_positive : contre systeme + outcome positif (gut beat signal)
 - against_negative : contre + outcome negatif (systeme avait raison)
 - neutral : outcome insignifiant (|return| < 3%)

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-06
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE position_decisions_context (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
            decision_id                 INTEGER,
            action                      TEXT NOT NULL
                                        CHECK(action IN ('buy', 'sell')),
            ticker                      TEXT NOT NULL,
            qty                         REAL NOT NULL,
            price                       REAL NOT NULL,
            -- Snapshot canonique au moment confirm
            regime                      TEXT,
            regime_score                REAL,
            bucket_act                  INTEGER,
            bucket_watch                INTEGER,
            bucket_calm                 INTEGER,
            bucket_silent               INTEGER,
            cluster_id                  TEXT,
            cluster_share_before        REAL,
            cluster_share_after         REAL,
            regime_warnings_json        TEXT,
            bias_warnings_json          TEXT,
            signals_30d_str             TEXT,
            -- Retrospective fields (filled by cron +30j)
            retrospective_30d_at        TEXT,
            retrospective_30d_outcome_pct  REAL,
            retrospective_30d_pnl_pct      REAL,
            retrospective_30d_verdict   TEXT
                                        CHECK(retrospective_30d_verdict IN (
                                            'aligned_positive', 'aligned_negative',
                                            'against_positive', 'against_negative',
                                            'neutral', NULL)),
            -- Retrospective fields (filled by cron +90j)
            retrospective_90d_at        TEXT,
            retrospective_90d_outcome_pct  REAL,
            retrospective_90d_pnl_pct      REAL,
            retrospective_90d_verdict   TEXT
                                        CHECK(retrospective_90d_verdict IN (
                                            'aligned_positive', 'aligned_negative',
                                            'against_positive', 'against_negative',
                                            'neutral', NULL))
        )
    """)
    op.execute(
        "CREATE INDEX idx_pdc_ticker ON position_decisions_context(ticker, created_at)"
    )
    op.execute(
        "CREATE INDEX idx_pdc_created ON position_decisions_context(created_at)"
    )
    op.execute(
        "CREATE INDEX idx_pdc_retro30 ON position_decisions_context(retrospective_30d_at, created_at)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_pdc_retro30")
    op.execute("DROP INDEX IF EXISTS idx_pdc_created")
    op.execute("DROP INDEX IF EXISTS idx_pdc_ticker")
    op.execute("DROP TABLE IF EXISTS position_decisions_context")
