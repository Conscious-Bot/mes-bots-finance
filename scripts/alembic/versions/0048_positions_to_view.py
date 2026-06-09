"""Swap positions table → VIEW dérivée — Option A étendue (cf SPEC_LEDGER §5).

Cf docs/SWAP_0048_PREREQUIS.md + red-team Olivier 09/06 :
  "Option A bien faite EST le single-source. Condition : prices.get() write-through
   price_history (✓ ligne 41 shared/prices.py) ET book.value_eur lit la même
   source (✓ via _cached_price_eur → get_current_price → price_history). Donc
   VUE A JOIN price_history + fx_history = canon, pas compromis."

Approche réversible : RENAME positions → positions_legacy_snapshot (PAS DROP).
Si runtime casse, downgrade restaure tout proprement.

La VUE expose les mêmes colonnes que l'ancienne table positions, dérivées de :
  - transactions (ledger source de vérité pour qty/PRU/realized_pnl/opened_at)
  - positions_meta (notes/status/account/wrapper)
  - price_history (dernier tick par ticker → last_price_native/currency/asof/source)
  - fx_history (dernier rate par paire → fx_rate_to_eur/fx_asof/fx_source)
  - dérivés : last_price_eur = last_price_native × fx_rate_to_eur

Conventions VUE :
  - avg_cost_currency = 'EUR' (book Olivier 100% EUR-payé via TR/PEA, fx déjà
    figé au moment du trade dans transactions.fx_at_trade)
  - fx_at_purchase = 1.0 (déprécié, cohérent EUR partout)
  - avg_cost_value = pru_eur (alias)
  - avg_cost_asof = opened_at (approximation : asof du baseline = premier achat)
  - last_updated = COALESCE(price_asof, opened_at) (asof granulaire ailleurs)
  - id = m.rowid (positions_meta rowid stable, satisfait les consumers qui ne
    s'attendent qu'à avoir un id intègre, pas une valeur stable historique)
"""
from __future__ import annotations

from alembic import op

revision = "0048"
down_revision = "0046"  # Note : 0047/0047b sont des scripts, pas des migrations
branch_labels = None
depends_on = None


VIEW_SQL = """
CREATE VIEW positions AS
WITH buys_agg AS (
    SELECT ticker,
           SUM(qty) AS qty_buy,
           MIN(trade_date) AS opened_at,
           SUM(qty * price_native + fees_native) / SUM(qty) AS pru_native,
           SUM(qty * price_native * fx_at_trade + fees_native * fx_at_trade) / SUM(qty) AS pru_eur,
           MAX(currency) AS currency_native
    FROM transactions WHERE side='BUY' GROUP BY ticker
),
sells_agg AS (
    SELECT s.ticker,
           SUM(s.qty) AS qty_sell,
           SUM(
             s.qty * s.price_native * s.fx_at_trade
           - s.fees_native * s.fx_at_trade
           - s.qty * (
               SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade)
                    / SUM(b.qty)
               FROM transactions b
               WHERE b.ticker = s.ticker AND b.side = 'BUY' AND b.trade_date < s.trade_date
             )
           ) AS realized_pnl_eur
    FROM transactions s WHERE s.side='SELL' GROUP BY s.ticker
),
latest_price AS (
    -- Utilise idx_px_ticker_asof (déjà indexé). MAX(asof) ≡ MAX(id) en pratique
    -- (insertions ordonnées temporellement) tout en utilisant le bon index → perf OK.
    SELECT p1.ticker,
           p1.price_native AS last_price_native,
           p1.currency AS last_price_currency,
           p1.asof AS price_asof,
           p1.source AS price_source
    FROM price_history p1
    WHERE p1.asof = (SELECT MAX(p2.asof) FROM price_history p2 WHERE p2.ticker = p1.ticker)
),
latest_fx AS (
    -- Utilise idx_fx_pair_asof. Même logique.
    SELECT fx1.base, fx1.quote, fx1.rate, fx1.asof, fx1.source
    FROM fx_history fx1
    WHERE fx1.asof = (
        SELECT MAX(fx2.asof) FROM fx_history fx2
        WHERE fx2.base = fx1.base AND fx2.quote = fx1.quote
    )
)
SELECT
    m.rowid AS id,
    m.ticker AS ticker,
    COALESCE(b.qty_buy, 0) - COALESCE(s.qty_sell, 0) AS qty,
    b.pru_eur AS avg_cost,
    b.pru_eur AS avg_cost_eur,
    b.pru_native AS avg_cost_native,
    'EUR' AS avg_cost_currency,
    b.pru_eur AS avg_cost_value,
    b.opened_at AS avg_cost_asof,
    1.0 AS fx_at_purchase,
    COALESCE(s.realized_pnl_eur, 0) AS realized_pnl,
    b.opened_at AS opened_at,
    COALESCE(lp.price_asof, b.opened_at) AS last_updated,
    lp.last_price_native,
    lp.last_price_currency,
    lp.price_asof,
    lp.price_source,
    lp.last_price_native * COALESCE(fx_eur.rate, 1.0) AS last_price_eur,
    COALESCE(fx_eur.rate, 1.0) AS fx_rate_to_eur,
    fx_eur.asof AS fx_asof,
    fx_eur.source AS fx_source,
    m.notes, m.status, m.account, m.wrapper
FROM positions_meta m
LEFT JOIN buys_agg b ON b.ticker = m.ticker
LEFT JOIN sells_agg s ON s.ticker = m.ticker
LEFT JOIN latest_price lp ON lp.ticker = m.ticker
LEFT JOIN latest_fx fx_eur ON fx_eur.base = lp.last_price_currency AND fx_eur.quote = 'EUR'
"""


def upgrade() -> None:
    # 1. RENAME (réversible) — préserve table pour rollback runtime
    op.execute("ALTER TABLE positions RENAME TO positions_legacy_snapshot")

    # 2. CREATE VIEW
    op.execute(VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS positions")
    op.execute("ALTER TABLE positions_legacy_snapshot RENAME TO positions")
