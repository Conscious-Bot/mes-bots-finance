"""thesis_erosion_classifications : persistance per-signal classifications LLM.

Avant : compute_thesis_erosion produisait des classifications {bears_on, relation,
confidence, ...} mais elles etaient volatiles in-memory, perdues apres l'agregat.
Impossible d'afficher "Canon erodes D1 conf 0.40" dans position-card.

Cette table persiste FK erosion_log_id + signal_id + classification complete.
Permet de re-rendre la timeline des signaux confrontes a la these depuis l'entree.

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-07
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE thesis_erosion_classifications (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            erosion_log_id    INTEGER NOT NULL REFERENCES thesis_erosion_log(id),
            signal_id         INTEGER NOT NULL,
            signal_source     TEXT NOT NULL CHECK(signal_source IN ('signals', 'chat')),
            bears_on          TEXT CHECK(bears_on IN ('driver', 'invalidation', 'none', NULL)),
            target_index      INTEGER,
            relation          TEXT CHECK(relation IN ('confirms', 'erodes', 'triggers', 'neutral', NULL)),
            confidence        REAL,
            materiality       REAL,
            rationale         TEXT,
            evidence_quote    TEXT
        )
    """)
    op.execute("""
        CREATE INDEX idx_erosion_class_log
        ON thesis_erosion_classifications(erosion_log_id)
    """)
    op.execute("""
        CREATE INDEX idx_erosion_class_signal
        ON thesis_erosion_classifications(signal_id, signal_source)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS thesis_erosion_classifications")
