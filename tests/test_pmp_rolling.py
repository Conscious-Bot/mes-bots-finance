"""Tests #127b — PMP roulant fiscal FR (shared/ledger_pmp.py).

Cf rectification Olivier 09/06 : 'PMP fiscal FR RESET le pool sur clôture
complète. La sous-requête corrélée VUE est exacte UNIQUEMENT sans re-BUY
après SELL. 8 tickers cassent la simplif. Sors la dérivation en Python.'

Couvre :
  1. PMP unchanged sur SELLs simples (no re-buy after sell)
  2. PMP recalcul correct sur BUY-SELL-BUY (sans full close)
  3. PMP reset à 0 sur full close, nouveau pool sur re-buy
  4. realized correct sur tous les cas
  5. Frais capitalisés (convention tax-FR)
  6. Garde régression : rolling == all-buys-avg quand BUY-only puis SELLs
"""
from __future__ import annotations

import sqlite3

import pytest

from shared.ledger_pmp import compute_pmp_realized


@pytest.fixture
def ledger_db():
    """In-memory SQLite avec schema transactions seul (suffit pour le helper)."""
    cx = sqlite3.connect(":memory:")
    cx.row_factory = sqlite3.Row
    cx.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, side TEXT NOT NULL,
            qty REAL NOT NULL CHECK(qty > 0),
            price_native REAL NOT NULL, fees_native REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL, fx_at_trade REAL NOT NULL,
            fx_is_derived INTEGER NOT NULL DEFAULT 0,
            trade_date TEXT NOT NULL, broker_trade_id TEXT,
            source TEXT NOT NULL, is_anchor INTEGER NOT NULL DEFAULT 0,
            notes TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    yield cx
    cx.close()


def _ins(cx, ticker, side, qty, price, date, fees=0.0):
    cx.execute("INSERT INTO transactions (ticker, side, qty, price_native, fees_native, "
               "currency, fx_at_trade, trade_date, source) "
               "VALUES (?, ?, ?, ?, ?, 'EUR', 1.0, ?, 'test')",
               (ticker, side, qty, price, fees, date))


# ============================================================================
# 1. PMP unchanged sur SELLs simples (no re-buy)
# ============================================================================


def test_pmp_unchanged_on_simple_sells(ledger_db):
    """BUY 10@10 → BUY 10@20 → SELL 5@15 → PMP doit rester 15 (= moyenne pondérée)."""
    _ins(ledger_db, "T", "BUY", 10, 10, "2025-01-01")
    _ins(ledger_db, "T", "BUY", 10, 20, "2025-02-01")
    _ins(ledger_db, "T", "SELL", 5, 15, "2025-03-01")
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "T")
    assert p.qty == pytest.approx(15.0, abs=1e-9)
    assert p.pmp_eur == pytest.approx(15.0, abs=1e-9)  # (10x10 + 10x20)/(10+10) = 15
    # realized = 5 x (15 - 15) = 0
    assert p.realized_pnl_eur == pytest.approx(0.0, abs=1e-9)
    assert p.n_closures == 0


# ============================================================================
# 2. PMP recalcul sur BUY-SELL-BUY (Olivier's example, sans full close)
# ============================================================================


def test_pmp_recalc_on_buy_sell_buy(ledger_db):
    """Cf Olivier red-team : BUY 10@10 → SELL 5@15 → BUY 5@20.

    Rolling : PMP final = (5x10 + 5x20) / 10 = 15 (CORRECT fiscal FR)
    All-buys (VUE buggy) : (10x10 + 5x20) / 15 = 13.33 (FAUX, pollué par qty vendue)
    """
    _ins(ledger_db, "T", "BUY", 10, 10, "2025-01-01")
    _ins(ledger_db, "T", "SELL", 5, 15, "2025-02-01")
    _ins(ledger_db, "T", "BUY", 5, 20, "2025-03-01")
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "T")
    assert p.qty == pytest.approx(10.0, abs=1e-9)
    # Rolling : pool après SELL = 5 @ PMP 10, puis +5 @ 20 → (5x10 + 5x20)/10 = 15
    assert p.pmp_eur == pytest.approx(15.0, abs=1e-9)
    # realized SELL = 5 x (15 - 10) = 25
    assert p.realized_pnl_eur == pytest.approx(25.0, abs=1e-9)
    assert p.n_closures == 0


# ============================================================================
# 3. Full close → reset → re-buy (Tesla pattern)
# ============================================================================


def test_full_close_resets_pool_then_rebuy(ledger_db):
    """BUY 10@10 → SELL 10@15 (close) → BUY 5@20 → PMP nouveau pool = 20."""
    _ins(ledger_db, "T", "BUY", 10, 10, "2025-01-01")
    _ins(ledger_db, "T", "SELL", 10, 15, "2025-02-01")  # full close
    _ins(ledger_db, "T", "BUY", 5, 20, "2025-03-01")
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "T")
    assert p.qty == pytest.approx(5.0, abs=1e-9)
    # PMP nouveau pool = juste le BUY post-close = 20
    assert p.pmp_eur == pytest.approx(20.0, abs=1e-9)
    # realized close = 10 x (15 - 10) = 50
    assert p.realized_pnl_eur == pytest.approx(50.0, abs=1e-9)
    assert p.n_closures == 1


def test_multiple_full_closes(ledger_db):
    """Cycle BUY-SELL-BUY-SELL-BUY (2 closures) — PMP final = dernier BUY."""
    _ins(ledger_db, "T", "BUY", 10, 10, "2025-01-01")
    _ins(ledger_db, "T", "SELL", 10, 12, "2025-02-01")  # close 1
    _ins(ledger_db, "T", "BUY", 10, 15, "2025-03-01")
    _ins(ledger_db, "T", "SELL", 10, 18, "2025-04-01")  # close 2
    _ins(ledger_db, "T", "BUY", 10, 25, "2025-05-01")
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "T")
    assert p.qty == pytest.approx(10.0, abs=1e-9)
    assert p.pmp_eur == pytest.approx(25.0, abs=1e-9)  # nouveau pool
    # realized = 10x(12-10) + 10x(18-15) = 20 + 30 = 50
    assert p.realized_pnl_eur == pytest.approx(50.0, abs=1e-9)
    assert p.n_closures == 2


# ============================================================================
# 4. Frais capitalisés (convention tax-FR)
# ============================================================================


def test_fees_capitalized_in_pmp(ledger_db):
    """BUY 100 @ 10 + fee 5 → PMP = (1000 + 5) / 100 = 10.05 (pas 10)."""
    _ins(ledger_db, "T", "BUY", 100, 10, "2025-01-01", fees=5)
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "T")
    assert p.pmp_eur == pytest.approx(10.05, abs=1e-9)


def test_sell_fees_deducted_from_proceeds(ledger_db):
    """BUY 100 @ 10 + fee 1 → SELL 50 @ 15 + fee 1.

    PMP = (1000 + 1) / 100 = 10.01
    realized = 50 x 15 - 1 - 50 x 10.01 = 750 - 1 - 500.5 = 248.50
    """
    _ins(ledger_db, "T", "BUY", 100, 10, "2025-01-01", fees=1)
    _ins(ledger_db, "T", "SELL", 50, 15, "2025-02-01", fees=1)
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "T")
    assert p.realized_pnl_eur == pytest.approx(248.50, abs=1e-9)


# ============================================================================
# 5. E2E replay Tesla pattern (la raison du fix)
# ============================================================================


def test_e2e_tesla_close_rebuy_matches_broker(ledger_db):
    """Reproduction simplifiée Tesla : BUY 3@320.90 → SELL 3@201.25 (close)
    → BUY 4.467653@344.65.

    Rolling correct : PMP nouveau pool ≈ 344.65 (= prix du BUY post-close)
    """
    _ins(ledger_db, "TSLA", "BUY",  3.0,      320.90, "2022-01-03", fees=1)
    _ins(ledger_db, "TSLA", "SELL", 3.0,      201.25, "2023-10-23", fees=1)
    _ins(ledger_db, "TSLA", "BUY",  4.467653, 344.65, "2025-11-24", fees=1)
    ledger_db.commit()

    p = compute_pmp_realized(ledger_db, "TSLA")
    # PMP nouveau pool = (4.467653 x 344.65 + 1) / 4.467653
    expected_pmp = (4.467653 * 344.65 + 1) / 4.467653
    assert p.pmp_eur == pytest.approx(expected_pmp, abs=0.01)
    assert p.n_closures == 1
    # realized close = 3 x (201.25 - pmp_pré_sell) - fees_sell
    # PMP pré-sell = (3 x 320.90 + 1) / 3 = 321.23
    # realized = 3 x 201.25 - 1 - 3 x 321.23 = 603.75 - 1 - 963.70 = -360.95
    expected_realized = 3 * 201.25 - 1 - 3 * ((3 * 320.90 + 1) / 3)
    assert p.realized_pnl_eur == pytest.approx(expected_realized, abs=0.01)


def test_pmp_reset_proves_old_cost_excluded(ledger_db):
    """REGRESSION GATE : démontre que le cost du lot fermé NE pollue PAS le PMP.

    Si on faisait all-buys-avg (VUE buggy), le BUY initial à 100 polluerait
    le pool même après fermeture totale du lot. Le rolling DOIT exclure ce coût.
    """
    # 1 BUY ridiculement cher, totalement vendu, puis 1 BUY normal
    _ins(ledger_db, "T", "BUY",  100, 1000.0, "2025-01-01")  # COST 100,000
    _ins(ledger_db, "T", "SELL", 100,    1.0, "2025-02-01")  # liquidation, énorme perte
    _ins(ledger_db, "T", "BUY",  100,   10.0, "2025-03-01")  # nouveau pool

    p = compute_pmp_realized(ledger_db, "T")
    # PMP rolling : nouveau pool isolé = 10 (correct)
    assert p.pmp_eur == pytest.approx(10.0, abs=1e-9)
    # VUE buggy (all-buys-avg) donnerait : (100x1000 + 100x10) / 200 = 505 (POLLUÉ par lot fermé)
    assert p.pmp_eur != pytest.approx(505.0, abs=1)
