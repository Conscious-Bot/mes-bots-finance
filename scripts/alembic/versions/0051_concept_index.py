"""LIVING GRAPH W0 — table concept_index (valeurs inline, fork-detection minimal).

Cf SPEC_LIVING_GRAPH.md §2 architecture V0 :
- concept_index = UNE table, valeurs inline (pas de FK vers datum_log)
- PK composite (concept_key, ticker, asof_bucket, source) → UPSERT idempotent
- datum_log NON créé en V0 (différé V1+, cf SPEC §0/§3/§4)

Le geste qui mécanise L29 (corriger calcul ≠ vérifier diffusion) :
plusieurs producteurs publient la même grandeur sémantique (concept_key) ;
si leurs valeurs divergent au-delà de ε → fork détecté au regen-end.

Discipline shared/storage.py = passerelle DB respectée (alembic uses op.execute).
"""
from __future__ import annotations

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE concept_index (
            concept_key  TEXT NOT NULL,
            ticker       TEXT NOT NULL DEFAULT '',
            asof_bucket  TEXT NOT NULL,
            source       TEXT NOT NULL,
            value        REAL NOT NULL,
            op           TEXT,
            degraded     INTEGER NOT NULL DEFAULT 0,
            confidence   REAL NOT NULL DEFAULT 1.0,
            logged_at    TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (concept_key, ticker, asof_bucket, source)
        )
    """)
    # Index pour scan rapide detect_forks par bucket
    op.execute("CREATE INDEX idx_concept_bucket ON concept_index(asof_bucket, concept_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_concept_bucket")
    op.execute("DROP TABLE IF EXISTS concept_index")
