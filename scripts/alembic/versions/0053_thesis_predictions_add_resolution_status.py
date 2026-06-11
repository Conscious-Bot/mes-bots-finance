"""SPEC_THESIS_ALPHA_RESOLVER §4.1 — axe lifecycle séparé du axe scoring.

ADD COLUMN resolution_status (lifecycle binaire 'resolved'/'abandoned')
DISTINCT de exclude_reason (axe scoring 'neutral'/'no_bet').

Mélanger les deux dans une seule enum = bug 2-référentiels banni
(SPEC §4.1). Cette migration ferme l'option avant qu'un implémenteur ne
propose de surcharger exclude_reason avec 'price_unavailable' (ce qui
aurait exigé recréation table → risque démesuré pour bénéfice
sémantiquement sale).

Pattern ADD COLUMN + DROP/CREATE trigger 2 :
- ADD COLUMN = O(1) métadonnée, zéro recréation de table
- Trigger 2 (resolve_writeonce) DOIT être recréé pour ajouter
  resolution_status à sa liste UPDATE OF (sinon mutable post-resolve,
  bug schéma)
- Triggers 1 (pose immuable) et 3 (no_delete) intacts
- Indexes intacts

Downgrade STRICT — ordre obligatoire SQLite :
1. Garde Python : refuse si lignes 'abandoned' existent (perte interdite).
   RAISE() SQL hors trigger = illégal SQLite, donc garde Python pur.
2. DROP TRIGGER (sinon DROP COLUMN bloqué : trigger référence la colonne)
3. DROP COLUMN resolution_status (SQLite ≥3.35, bundle Python 3.14 OK)
4. CREATE TRIGGER étroit (liste OF sans resolution_status — état 0052)

Message RAISE du trigger 2 byte-identique à 0052 ligne 103 (préservation
sémantique — recréation = identité, pas dérive).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ADD COLUMN resolution_status (axe lifecycle distinct de exclude_reason)
    op.execute("""
        ALTER TABLE thesis_predictions
        ADD COLUMN resolution_status TEXT
        CHECK(resolution_status IS NULL OR resolution_status IN ('resolved', 'abandoned'))
    """)

    # 2. DROP+RECREATE trigger 2 pour inclure resolution_status dans la
    #    liste UPDATE OF (sinon mutable post-resolved_at = bug schéma).
    op.execute("DROP TRIGGER thesis_predictions_resolve_writeonce")
    op.execute("""
        CREATE TRIGGER thesis_predictions_resolve_writeonce
        BEFORE UPDATE OF
            resolved_at, resolve_price_native, alpha_realized_pct,
            direction_correct, magnitude_score, exclude_reason,
            resolution_status
        ON thesis_predictions
        FOR EACH ROW
        WHEN OLD.resolved_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'thesis_predictions resolve columns are write-once : déjà résolu, pas de re-résolution (SPEC §2.2). Pour corriger : INSERT une ligne audit séparée.');
        END
    """)


def downgrade() -> None:
    # ORDRE OBLIGATOIRE — toute permutation pète :
    # - DROP COLUMN avant DROP TRIGGER → SQLite refuse (trigger référence col)
    # - Pas de garde Python → perte silencieuse de données 'abandoned'
    bind = op.get_bind()

    # Étape 1 : garde Python (RAISE() SQL hors trigger = illégal)
    n_abandoned = bind.execute(
        text("SELECT COUNT(*) FROM thesis_predictions WHERE resolution_status='abandoned'")
    ).scalar() or 0
    if n_abandoned > 0:
        raise RuntimeError(
            f"downgrade 0053 → 0052 BLOQUÉ : {n_abandoned} ligne(s) avec "
            f"resolution_status='abandoned'. Perte de données interdite. "
            f"Audit + transition manuelle requise (export track-record avant) "
            f"sinon les abandons re-deviennent indistinguables des résolutions normales."
        )

    # Étape 2 : DROP TRIGGER (libère la référence sur resolution_status)
    op.execute("DROP TRIGGER thesis_predictions_resolve_writeonce")

    # Étape 3 : DROP COLUMN (maintenant possible)
    op.execute("ALTER TABLE thesis_predictions DROP COLUMN resolution_status")

    # Étape 4 : CREATE TRIGGER étroit (liste OF sans resolution_status, état 0052)
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
