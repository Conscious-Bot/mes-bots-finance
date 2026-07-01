"""VUE positions : clamp le dust flottant de qty à 0.

Audit cohérence 30/06 : AMD affiche qty=-1.8e-07 (invariant test_positions_qty
_non_negative ROUGE). Cause : la qty de la vue = SUM(BUY) - SUM(SELL) sur les
transactions ; une position soldée dont les 19 tx ne nettent pas exactement à 0
laisse un résidu flottant sub-micro-share. -0.00000018 share est physiquement
absurde (brokers arrondissent à ~6 décimales) → pur artefact.

Fix chirurgical : CASE WHEN ABS(net) < 1e-6 THEN 0 ELSE net END.
Ne touche QUE le dust (positions soldées) ; toute vraie position fractionnaire
(MU 1.465…, Hynix 1.343…) reste byte-identique (net >> 1e-6). Aucun autre champ
de la vue ne change vs 0049 (fail-closed avg_cost/realized préservé).

Migration : DROP VIEW + CREATE VIEW (stateless, zéro donnée touchée).
Downgrade : rétablit la vue 0049 (net non clampé).
"""
from __future__ import annotations

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


# Identique à 0049 VIEW_SQL_FAILCLOSED, SEULE la ligne `qty` change (clamp dust).
VIEW_SQL_CLAMPED = """
CREATE VIEW positions AS
WITH buys_agg AS (
    SELECT ticker,
           SUM(qty) AS qty_buy,
           MIN(trade_date) AS opened_at,
           MAX(currency) AS currency_native
    FROM transactions WHERE side='BUY' GROUP BY ticker
),
sells_agg AS (
    SELECT ticker, SUM(qty) AS qty_sell
    FROM transactions WHERE side='SELL' GROUP BY ticker
),
latest_price AS (
    SELECT p1.ticker, p1.price_native AS last_price_native,
           p1.currency AS last_price_currency,
           p1.asof AS price_asof, p1.source AS price_source
    FROM price_history p1
    WHERE p1.asof = (SELECT MAX(p2.asof) FROM price_history p2 WHERE p2.ticker = p1.ticker)
),
latest_fx AS (
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
    CASE WHEN ABS(COALESCE(b.qty_buy, 0) - COALESCE(s.qty_sell, 0)) < 1e-6
         THEN 0
         ELSE COALESCE(b.qty_buy, 0) - COALESCE(s.qty_sell, 0) END AS qty,
    -- PMP/realized = NULL fail-closed : utiliser shared.book.get_held_lines() ou
    -- shared.ledger_pmp.compute_pmp_realized() (rolling fiscal FR correct).
    NULL AS avg_cost,
    NULL AS avg_cost_eur,
    NULL AS avg_cost_native,
    'EUR' AS avg_cost_currency,
    NULL AS avg_cost_value,
    b.opened_at AS avg_cost_asof,
    1.0 AS fx_at_purchase,
    NULL AS realized_pnl,
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


# Restauration exacte de la vue 0049 (net non clampé).
VIEW_SQL_0049_RESTORE = """
CREATE VIEW positions AS
WITH buys_agg AS (
    SELECT ticker,
           SUM(qty) AS qty_buy,
           MIN(trade_date) AS opened_at,
           MAX(currency) AS currency_native
    FROM transactions WHERE side='BUY' GROUP BY ticker
),
sells_agg AS (
    SELECT ticker, SUM(qty) AS qty_sell
    FROM transactions WHERE side='SELL' GROUP BY ticker
),
latest_price AS (
    SELECT p1.ticker, p1.price_native AS last_price_native,
           p1.currency AS last_price_currency,
           p1.asof AS price_asof, p1.source AS price_source
    FROM price_history p1
    WHERE p1.asof = (SELECT MAX(p2.asof) FROM price_history p2 WHERE p2.ticker = p1.ticker)
),
latest_fx AS (
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
    NULL AS avg_cost,
    NULL AS avg_cost_eur,
    NULL AS avg_cost_native,
    'EUR' AS avg_cost_currency,
    NULL AS avg_cost_value,
    b.opened_at AS avg_cost_asof,
    1.0 AS fx_at_purchase,
    NULL AS realized_pnl,
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
    op.execute("DROP VIEW IF EXISTS positions")
    op.execute(VIEW_SQL_CLAMPED)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS positions")
    op.execute(VIEW_SQL_0049_RESTORE)
