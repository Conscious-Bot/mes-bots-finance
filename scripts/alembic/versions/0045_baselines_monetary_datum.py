"""SOCLE Phase 4 : baselines monétaires migrent vers Datum[Monetary] -- SCHÉMA SEULEMENT.

Cf SPEC_MONEY_INVARIANT.md §6.3 + red-team Olivier 08/06 nuit :
  "Migration 0045 = schéma SEULEMENT : add *_value/*_currency/*_asof + trigger
   write-once. Portable, idempotente, rejoue partout sans backup."

Cette migration ne touche QUE le schéma — pas la donnée. Elle est portable :
test fresh DB, CI, futur clone, tous peuvent la rejouer sans dépendre d'un
fichier backup local.

Le restore de la donnée native (depuis bot.db.backup_session_close_20260606_192531)
est un acte one-shot séparé : `scripts/restore_native_baselines.py`. Lancé une
fois sur la prod, idempotent-gardé (skip si déjà restauré). Pas un mécanisme
permanent — un acte ponctuel de recovery pré-spec.

Effet schéma (cette migration) :
  - ADD 4×3 colonnes theses : *_value, *_currency, *_asof
    pour entry, stop, target_partial, target_full
  - ADD 2 colonnes theses : entry_fx_at_call, entry_fx_at_call_asof
  - ADD 2 colonnes positions : avg_cost_value, avg_cost_asof
    (avg_cost_currency existe déjà depuis 0044)
  - CREATE 12 TRIGGER write-once sur theses (cf §3 spec)
  - DROP + RECREATE trigger F7 (theses_active_must_have_inputs) sur _value
    car référence l'ancienne colonne entry_price qui DOIT être DROP plus tard

Revision ID: 0045
Revises: 0044
"""

from __future__ import annotations

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def _currency_case_expr(ticker_col: str) -> str:
    """SQL CASE pour dériver la devise depuis le ticker (.T/.KS/.PA/.AS/défaut USD).

    Source unique : convention suffix-ticker, alignée sur shared.prices.get_currency_for_ticker.
    """
    return f"""
        CASE
            WHEN {ticker_col} LIKE '%.T' THEN 'JPY'
            WHEN {ticker_col} LIKE '%.KS' THEN 'KRW'
            WHEN {ticker_col} LIKE '%.PA' THEN 'EUR'
            WHEN {ticker_col} LIKE '%.AS' THEN 'EUR'
            ELSE 'USD'
        END
    """.strip()


def upgrade() -> None:
    # 1. ADD colonnes Datum[Monetary] triplet sur theses
    for col_base in ("entry", "stop", "target_partial", "target_full"):
        op.execute(f"ALTER TABLE theses ADD COLUMN {col_base}_value REAL")
        op.execute(f"ALTER TABLE theses ADD COLUMN {col_base}_currency TEXT")
        op.execute(f"ALTER TABLE theses ADD COLUMN {col_base}_asof TEXT")

    # entry_fx_at_call (EUR-view secondaire, degraded si fx_history@opened_at indispo)
    op.execute("ALTER TABLE theses ADD COLUMN entry_fx_at_call REAL")
    op.execute("ALTER TABLE theses ADD COLUMN entry_fx_at_call_asof TEXT")

    # 2. ADD colonnes Datum[Monetary] sur positions.avg_cost
    # avg_cost_currency existe déjà depuis migration 0044 -- on la garde et la réutilise.
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_value REAL")
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_asof TEXT")

    # 3. PAS de restore ici -- la donnée native est restaurée par le script
    # one-shot `scripts/restore_native_baselines.py`, lancé séparément sur prod.
    # Cette migration est portable : fresh test DB, CI, futur clone, tous la
    # rejouent sans dépendre d'un fichier backup local.

    # 4. CREATE TRIGGER write-once UNIQUEMENT sur entry_* (immuable, fait historique).
    # stop/target_partial/target_full sont des DÉCISIONS VIVANTES (trailing stop,
    # re-target sur news) — substrat mutable + history (cf CANONICAL_MAP §2,
    # red-team Olivier 08/06 nuit). Les figer write-once = friction §3 à chaque
    # ajustement de gestion = absurde.
    #
    # entry_price = prix à l'appel de la thèse, FIGÉ pour le track-record du jugement.
    # Le UPDATE entry := avg_cost (vecteur du clobber 06/06) reste fermé.
    for col_suffix in ("value", "currency", "asof"):
        full_col = f"entry_{col_suffix}"
        op.execute(f"""
            CREATE TRIGGER theses_{full_col}_writeonce
            BEFORE UPDATE OF {full_col} ON theses
            FOR EACH ROW
            WHEN OLD.{full_col} IS NOT NULL AND OLD.{full_col} != NEW.{full_col}
            BEGIN
                SELECT RAISE(ABORT,
                    '{full_col} is write-once post-open (cf SPEC_MONEY_INVARIANT §3 + L28)'
                );
            END;
        """)


def downgrade() -> None:
    # Drop triggers
    for col_base in ("entry", "stop", "target_partial", "target_full"):
        for col_suffix in ("value", "currency", "asof"):
            op.execute(f"DROP TRIGGER IF EXISTS theses_{col_base}_{col_suffix}_writeonce")

    # Re-add legacy columns (sans data -- la migration upgrade est destructive)
    op.execute("ALTER TABLE theses ADD COLUMN entry_price REAL")
    op.execute("ALTER TABLE theses ADD COLUMN stop_price REAL")
    op.execute("ALTER TABLE theses ADD COLUMN target_partial REAL")
    op.execute("ALTER TABLE theses ADD COLUMN target_full REAL")
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost REAL")
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_eur REAL")
    op.execute("ALTER TABLE positions ADD COLUMN avg_cost_native REAL")
    op.execute("ALTER TABLE positions ADD COLUMN fx_at_purchase REAL")

    # Drop Monetary columns
    for col_base in ("entry", "stop", "target_partial", "target_full"):
        for col_suffix in ("value", "currency", "asof"):
            op.execute(f"ALTER TABLE theses DROP COLUMN {col_base}_{col_suffix}")
    op.execute("ALTER TABLE theses DROP COLUMN entry_fx_at_call")
    op.execute("ALTER TABLE theses DROP COLUMN entry_fx_at_call_asof")
    op.execute("ALTER TABLE positions DROP COLUMN avg_cost_value")
    op.execute("ALTER TABLE positions DROP COLUMN avg_cost_asof")
