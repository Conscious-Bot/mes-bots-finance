"""prediction_integrity_log : commit-reveal chain pour predictions (hiding obligatoire).

Architecture (catch red-team) : chain DISTINCT du thesis_integrity_log.
- theses = narratif transparent (chain visible)
- predictions = commit-reveal (payload_json + nonce PRIVE dans bot.db,
  ledger public exporte hash chain SEUL, payload revele a la resolution)

Pourquoi hiding : exporter payload_json predictions en clair = teleguider
positions live a chaque ancrage. Solution : public voit hash + ancrage OTS,
contenu reste prive jusqu'au reveal (outcome).

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-07
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE prediction_integrity_log (
            seq           INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id INTEGER NOT NULL REFERENCES predictions(id),
            captured_at   TEXT NOT NULL DEFAULT (datetime('now')),
            payload_json  TEXT NOT NULL,
            prev_hash     TEXT NOT NULL,
            chain_hash    TEXT NOT NULL
        )
    """)
    # Idempotence garde : 1 maille MAX par prediction_id
    op.execute(
        "CREATE UNIQUE INDEX idx_predint_pred ON prediction_integrity_log(prediction_id)"
    )
    # Verify_chain efficiency
    op.execute(
        "CREATE INDEX idx_predint_seq ON prediction_integrity_log(seq)"
    )
    # Chain_hash uniqueness (defense double-insert)
    op.execute(
        "CREATE UNIQUE INDEX idx_predint_chain_hash ON prediction_integrity_log(chain_hash)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_predint_chain_hash")
    op.execute("DROP INDEX IF EXISTS idx_predint_seq")
    op.execute("DROP INDEX IF EXISTS idx_predint_pred")
    op.execute("DROP TABLE IF EXISTS prediction_integrity_log")
