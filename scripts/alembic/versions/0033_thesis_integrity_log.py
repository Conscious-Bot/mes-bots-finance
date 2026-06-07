"""A1 : thesis_integrity_log append-only hash-chained table.

Spec red-team 07/06 nuit DECISION_QUALITY_ENGINE A1. Pattern monitor_pattern
(append-only, no updates apres insert, chain hash sha256(prev+payload)).

Sans A4 (anchor externe git tag signe / OpenTimestamps), A1-A3 = R1 theater
(la chain peut etre reecrite silencieusement). A4 inscrit anchor_ref qui
prouve l'etat chain a T0.

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-07
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE thesis_integrity_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            seq             INTEGER NOT NULL,
            thesis_id       INTEGER NOT NULL,
            captured_at     TEXT NOT NULL DEFAULT (datetime('now')),
            payload_json    TEXT NOT NULL,
            prev_hash       TEXT NOT NULL,
            chain_hash      TEXT NOT NULL UNIQUE,
            anchor_ref      TEXT
        )
    """)
    # Index : recompute chain par seq order
    op.execute(
        "CREATE INDEX idx_til_seq ON thesis_integrity_log(seq)"
    )
    # Index : lookup par thesis
    op.execute(
        "CREATE INDEX idx_til_thesis ON thesis_integrity_log(thesis_id, captured_at)"
    )
    # Unicite seq (append-only monotone)
    op.execute(
        "CREATE UNIQUE INDEX idx_til_seq_unique ON thesis_integrity_log(seq)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_til_seq_unique")
    op.execute("DROP INDEX IF EXISTS idx_til_thesis")
    op.execute("DROP INDEX IF EXISTS idx_til_seq")
    op.execute("DROP TABLE IF EXISTS thesis_integrity_log")
