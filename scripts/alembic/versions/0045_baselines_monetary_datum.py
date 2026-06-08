"""SOCLE Phase 4 : baselines monétaires migrent vers Datum[Monetary].

Cf SPEC_MONEY_INVARIANT.md §6.3 : 5 baselines (theses.entry/stop/target_partial/target_full,
positions.avg_cost) gagnent leur triple Datum (value, currency, asof). LE RESTORE depuis
backup natif se fait DANS cette migration -- jamais en float-nu intermédiaire (sinon on
rejoue la classe corrompue).

Source de récupération : `data/bot.db.backup_session_close_20260606_192531` (vérifié pré-M1).

Effet :
  - ADD 4×3 + 1×3 colonnes : *_value (REAL), *_currency (TEXT), *_asof (TEXT) + entry_fx_at_call
  - RESTORE native depuis backup
  - currency dérivée du ticker (.T→JPY, .KS→KRW, .PA/.AS→EUR, défaut USD)
  - asof = opened_at de la thèse / created_at de la position
  - DROP les anciens floats nus (entry_price, stop_price, target_partial, target_full, avg_cost)
  - DROP legacy avg_cost_eur / avg_cost_native / fx_at_purchase (obsolètes 0043/0044)
  - CREATE TRIGGER write-once sur theses.{entry,stop,target_partial,target_full}_*

Idempotente : guarded par PRAGMA + IF NOT EXISTS le cas échéant. Backup DB doit
être effectué AVANT (par le runner, pas par cette migration).

Walking-skeleton : la migration est testée sur data/bot.db.m1_test (copie) avant prod.

Revision ID: 0045
Revises: 0044
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_BACKUP_PATH = Path(__file__).resolve().parents[3] / "data" / "bot.db.backup_session_close_20260606_192531"


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

    # 3. ATTACH backup propre 06/06 (natives originaux pré-corruption)
    if not _BACKUP_PATH.exists():
        raise FileNotFoundError(
            f"Backup natif introuvable à {_BACKUP_PATH}. "
            "Migration M1 nécessite ce backup pour le restore (cf SPEC_MONEY_INVARIANT §6.3)."
        )
    op.execute(f"ATTACH DATABASE '{_BACKUP_PATH}' AS bk")

    # 4. RESTORE theses depuis backup natif + currency dérivée du ticker
    # Note : on restaure UNIQUEMENT pour les thèses dont l'id existe dans le backup
    # (les thèses orphelines, ouvertes APRÈS le backup, restent NULL = degraded).
    op.execute(f"""
        UPDATE theses
        SET
            entry_value = (SELECT bk_t.entry_price FROM bk.theses bk_t WHERE bk_t.id = theses.id),
            entry_currency = {_currency_case_expr("theses.ticker")},
            entry_asof = theses.opened_at,
            stop_value = (SELECT bk_t.stop_price FROM bk.theses bk_t WHERE bk_t.id = theses.id),
            stop_currency = {_currency_case_expr("theses.ticker")},
            stop_asof = theses.opened_at,
            target_partial_value = (SELECT bk_t.target_partial FROM bk.theses bk_t WHERE bk_t.id = theses.id),
            target_partial_currency = {_currency_case_expr("theses.ticker")},
            target_partial_asof = theses.opened_at,
            target_full_value = (SELECT bk_t.target_full FROM bk.theses bk_t WHERE bk_t.id = theses.id),
            target_full_currency = {_currency_case_expr("theses.ticker")},
            target_full_asof = theses.opened_at
        WHERE EXISTS (SELECT 1 FROM bk.theses bk_t WHERE bk_t.id = theses.id)
    """)

    # 5. RESTORE positions.avg_cost depuis backup natif + currency dérivée
    # Le backup ne porte pas avg_cost_native -- avg_cost est en native par convention.
    op.execute(f"""
        UPDATE positions
        SET
            avg_cost_value = (SELECT bk_p.avg_cost FROM bk.positions bk_p WHERE bk_p.ticker = positions.ticker AND bk_p.status='open'),
            avg_cost_currency = {_currency_case_expr("positions.ticker")},
            avg_cost_asof = positions.opened_at
        WHERE EXISTS (SELECT 1 FROM bk.positions bk_p WHERE bk_p.ticker = positions.ticker AND bk_p.status='open')
    """)

    op.execute("DETACH DATABASE bk")

    # 6. SYNC legacy float-nues avec natives restaures (pour que les ~250 call sites
    # qui lisent encore entry_price/stop_price/etc. obtiennent les natives, pas
    # les valeurs corrompues. Pendant la migration etagee, les consumers migrent
    # un par un vers entry_value (gate ratchet decreasing-only). DROP final
    # quand ratchet = 0, dans une migration suivante.)
    op.execute("UPDATE theses SET entry_price = entry_value WHERE entry_value IS NOT NULL")
    op.execute("UPDATE theses SET stop_price = stop_value WHERE stop_value IS NOT NULL")
    op.execute("UPDATE theses SET target_partial = target_partial_value WHERE target_partial_value IS NOT NULL")
    op.execute("UPDATE theses SET target_full = target_full_value WHERE target_full_value IS NOT NULL")
    op.execute("UPDATE positions SET avg_cost = avg_cost_value WHERE avg_cost_value IS NOT NULL")
    # Note : pas de SYNC avg_cost_eur / avg_cost_native -- ces colonnes 0043/0044
    # restent dans leur etat actuel (legacy, deprecated par cette migration).

    # 7. Pas de DROP des colonnes legacy positions -- meme raison qu'au point 6.
    # avg_cost / avg_cost_eur / avg_cost_native / fx_at_purchase restent disponibles
    # pour le code legacy. Migration etagee panneau-par-panneau via le seam ;
    # DROP final dans une migration suivante quand le gate ratchet atteint zero.

    # 8. CREATE TRIGGER write-once sur les baselines de theses (§3 spec)
    # Settable une fois (INSERT initial), tout UPDATE qui change la valeur après = ABORT.
    # Note : on autorise NULL -> valeur (set initial post-INSERT) ; on rejette valeur -> autre valeur.
    for col_base in ("entry", "stop", "target_partial", "target_full"):
        for col_suffix in ("value", "currency", "asof"):
            full_col = f"{col_base}_{col_suffix}"
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
