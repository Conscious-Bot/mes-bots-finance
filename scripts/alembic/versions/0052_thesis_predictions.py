"""SPEC_THESIS_ALPHA_RESOLVER §2.2 — table thesis_predictions append-only hybride.

Pattern :
- Colonnes POSE : immuables post-insert (trigger 1)
- Colonnes RESOLVE : write-once NULL→valeur, pas de re-resolution (trigger 2)
- DELETE bloqué (trigger 3)

Contrat writer (pièce 3) : la résolution doit être UN seul UPDATE atomique
(tous les resolve cols d'un coup, resolved_at inclus). Si le writer splitte
en plusieurs UPDATE, le 2e post-resolved_at se fait mordre par trigger 2
parce que WHEN OLD.resolved_at IS NOT NULL devient true après le 1er UPDATE.

Couches encodées :
- direction_correct INTEGER : 1=correct, 0=incorrect, NULL=exclu agrégation
- exclude_reason TEXT : 'neutral' (alpha plat) ou 'no_bet' (delta minuscule)
- Cohérence implicite : direction_correct NULL ⟺ exclude_reason non-NULL
  (pas de CHECK croisé = retenue L19, les 2 champs encodent ensemble)
"""
from __future__ import annotations

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE thesis_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- ============================================================
            -- POSE (asof) — immuable post-insert (trigger 1)
            -- ============================================================
            ticker TEXT NOT NULL,
            asof DATE NOT NULL,
            asof_price_native REAL NOT NULL CHECK(asof_price_native > 0),
            native_currency TEXT NOT NULL,
            pt_consensus_raw REAL NOT NULL CHECK(pt_consensus_raw > 0),
            pt_consensus_currency TEXT NOT NULL,
            pt_native_asof REAL NOT NULL CHECK(pt_native_asof > 0),
            fx_at_asof REAL NOT NULL CHECK(fx_at_asof > 0),
            your_target_native REAL NOT NULL CHECK(your_target_native > 0),
            your_delta_native_pct REAL NOT NULL,
            confidence REAL CHECK(confidence IS NULL OR (confidence > 0 AND confidence <= 1)),
            thesis_summary TEXT NOT NULL,
            resolve_due_date DATE NOT NULL,
            source TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            -- ============================================================
            -- RESOLVE (à resolve_due_date) — write-once NULL→valeur (trigger 2)
            -- ============================================================
            resolved_at TEXT,
            resolve_price_native REAL CHECK(resolve_price_native IS NULL OR resolve_price_native > 0),
            alpha_realized_pct REAL,
            direction_correct INTEGER CHECK(direction_correct IS NULL OR direction_correct IN (0, 1)),
            magnitude_score REAL CHECK(magnitude_score IS NULL OR (magnitude_score >= 0 AND magnitude_score <= 1)),
            exclude_reason TEXT CHECK(exclude_reason IS NULL OR exclude_reason IN ('neutral', 'no_bet')),

            -- Anti-doublon métier : pas de re-pose identique (même target, même asof)
            UNIQUE(ticker, asof, your_target_native)
        )
    """)

    # Index pour le job resolver : trouver vite les paris arrivés à maturité non résolus
    op.execute("CREATE INDEX idx_thesis_predictions_due ON thesis_predictions(resolve_due_date) WHERE resolved_at IS NULL")
    op.execute("CREATE INDEX idx_thesis_predictions_ticker_asof ON thesis_predictions(ticker, asof)")

    # ============================================================
    # Trigger 1 : POSE columns immuables post-insert
    # ============================================================
    op.execute("""
        CREATE TRIGGER thesis_predictions_pose_writeonce
        BEFORE UPDATE OF
            ticker, asof, asof_price_native, native_currency,
            pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
            your_target_native, your_delta_native_pct, confidence, thesis_summary,
            resolve_due_date, source, notes, created_at
        ON thesis_predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'thesis_predictions pose columns are immutable post-insert (SPEC §2.2 / L26 append-only). Pour corriger : INSERT une nouvelle ligne, ne PAS update.');
        END
    """)

    # ============================================================
    # Trigger 2 : RESOLVE columns write-once (NULL→valeur OK, re-résolution RAISE)
    # exclude_reason inclus dans la liste : sinon il resterait mutable post-résolution.
    # ============================================================
    op.execute("""
        CREATE TRIGGER thesis_predictions_resolve_writeonce
        BEFORE UPDATE OF
            resolved_at, resolve_price_native, alpha_realized_pct,
            direction_correct, magnitude_score, exclude_reason
        ON thesis_predictions
        FOR EACH ROW
        WHEN OLD.resolved_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'thesis_predictions resolve columns are write-once : déjà résolu, pas de re-résolution (SPEC §2.2). Pour corriger : INSERT une ligne audit séparée.');
        END
    """)

    # ============================================================
    # Trigger 3 : DELETE bloqué (append-only strict)
    # ============================================================
    op.execute("""
        CREATE TRIGGER thesis_predictions_no_delete
        BEFORE DELETE ON thesis_predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'thesis_predictions append-only : DELETE interdit. Le track-record alpha exige l''immutabilité historique (SPEC §2.2).');
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS thesis_predictions_no_delete")
    op.execute("DROP TRIGGER IF EXISTS thesis_predictions_resolve_writeonce")
    op.execute("DROP TRIGGER IF EXISTS thesis_predictions_pose_writeonce")
    op.execute("DROP INDEX IF EXISTS idx_thesis_predictions_ticker_asof")
    op.execute("DROP INDEX IF EXISTS idx_thesis_predictions_due")
    op.execute("DROP TABLE IF EXISTS thesis_predictions")
