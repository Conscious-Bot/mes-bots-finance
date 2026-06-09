"""VUE positions : NULL sur avg_cost*/realized_pnl — fail-closed L15.

Cf rectification Olivier 09/06 soir : 'La VUE garde le PMP all-buys faux
(8 tickers) = mensonge-en-prod différable = le réflexe qu'on dénonce, v2.
Incohérence VUE≠BookLine = violation L27 ré-introduite. NULL maintenant,
pas en 0049 différé.'

Le helper rolling `shared/ledger_pmp.compute_pmp_realized()` est la source
canonique unique du PMP fiscal FR (CGI : reset pool sur close complète,
rolling sur re-buy après SELL). La sous-requête corrélée SQL utilisée
jusqu'ici dans la VUE est exacte UNIQUEMENT en BUY-only puis SELLs sans
re-buy. 8 tickers ont des cycles partial-SELL→re-BUY qui faussent la VUE.

Fail-closed L15 : un NULL est honnête, un nombre faux est un mensonge.
Mieux qu'un consumer SQL-direct lise NULL et échoue bruyamment que
silencieusement consomme un PMP faux. Force la migration des consumers
vers BookLine (`shared/book.get_held_lines()`) ou helper rolling direct.

Migration :
  - DROP VIEW positions
  - CREATE VIEW positions avec mêmes colonnes mais avg_cost*/realized_pnl = NULL
  - Tous les autres champs (qty, opened_at, market live, meta) inchangés

Downgrade : rétablit la VUE all-buys via 0048 (sous-requête corrélée originale).
"""
from __future__ import annotations

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


VIEW_SQL_FAILCLOSED = """
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


VIEW_SQL_0048_RESTORE = """
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
    m.rowid AS id, m.ticker AS ticker,
    COALESCE(b.qty_buy, 0) - COALESCE(s.qty_sell, 0) AS qty,
    b.pru_eur AS avg_cost, b.pru_eur AS avg_cost_eur, b.pru_native AS avg_cost_native,
    'EUR' AS avg_cost_currency, b.pru_eur AS avg_cost_value,
    b.opened_at AS avg_cost_asof, 1.0 AS fx_at_purchase,
    COALESCE(s.realized_pnl_eur, 0) AS realized_pnl,
    b.opened_at AS opened_at, COALESCE(lp.price_asof, b.opened_at) AS last_updated,
    lp.last_price_native, lp.last_price_currency, lp.price_asof, lp.price_source,
    lp.last_price_native * COALESCE(fx_eur.rate, 1.0) AS last_price_eur,
    COALESCE(fx_eur.rate, 1.0) AS fx_rate_to_eur,
    fx_eur.asof AS fx_asof, fx_eur.source AS fx_source,
    m.notes, m.status, m.account, m.wrapper
FROM positions_meta m
LEFT JOIN buys_agg b ON b.ticker = m.ticker
LEFT JOIN sells_agg s ON s.ticker = m.ticker
LEFT JOIN latest_price lp ON lp.ticker = m.ticker
LEFT JOIN latest_fx fx_eur ON fx_eur.base = lp.last_price_currency AND fx_eur.quote = 'EUR'
"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS positions")
    op.execute(VIEW_SQL_FAILCLOSED)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS positions")
    op.execute(VIEW_SQL_0048_RESTORE)
