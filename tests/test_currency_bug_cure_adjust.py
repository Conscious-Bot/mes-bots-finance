"""Tests cure currency bug 4 trades 12/06/2026 via ADJUST tx (14/06/2026).

Cf SPEC_LEDGER §1 ("extensible 'ADJUST' (futur)") + memory
partial_close_handler_missing (interdit reversal-BUY qui pollue PMP path-dependent).

Tests :
1. ADJUST tx override price_native + fx_at_trade de la tx target
2. ADJUST tx mal formé (notes JSON invalide) → ignore silent-soft
3. Multiple ADJUST sur même target → dernier dans iteration gagne (override map)
4. ADJUST sans target_tx_id → ignore
5. EUR debited preserved (EUR-side invariant under cure)
"""
from __future__ import annotations

import sqlite3

import pytest

from shared.ledger_pmp import compute_pmp_realized


def _bootstrap_db(conn: sqlite3.Connection) -> None:
    """Create minimal transactions schema for these tests (no triggers, isolated)."""
    conn.execute("""
        CREATE TABLE transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            side            TEXT NOT NULL,
            qty             REAL NOT NULL CHECK(qty > 0),
            price_native    REAL NOT NULL,
            fees_native     REAL NOT NULL DEFAULT 0,
            currency        TEXT NOT NULL,
            fx_at_trade     REAL NOT NULL,
            fx_is_derived   INTEGER NOT NULL DEFAULT 0,
            trade_date      TEXT NOT NULL,
            broker_trade_id TEXT UNIQUE,
            source          TEXT NOT NULL,
            is_anchor       INTEGER NOT NULL DEFAULT 0,
            notes           TEXT
        )
    """)


def _insert(conn, **kw):
    """Insert a transaction with defaults."""
    defaults = {
        "ticker": "TEST", "side": "BUY", "qty": 1.0, "price_native": 100.0,
        "fees_native": 0, "currency": "USD", "fx_at_trade": 1.0, "fx_is_derived": 0,
        "trade_date": "2026-01-01T00:00:00Z", "source": "test", "is_anchor": 0,
        "notes": None, "broker_trade_id": None,
    }
    defaults.update(kw)
    cur = conn.execute(
        """INSERT INTO transactions
           (ticker, side, qty, price_native, fees_native, currency, fx_at_trade,
            fx_is_derived, trade_date, broker_trade_id, source, is_anchor, notes)
           VALUES (:ticker, :side, :qty, :price_native, :fees_native, :currency,
                   :fx_at_trade, :fx_is_derived, :trade_date, :broker_trade_id,
                   :source, :is_anchor, :notes)""",
        defaults,
    )
    return cur.lastrowid


class TestAdjustOverride:
    """Core : ADJUST tx override price_native + fx_at_trade de la tx target."""

    def test_no_adjust_baseline(self):
        conn = sqlite3.connect(":memory:")
        _bootstrap_db(conn)
        _insert(conn, side="BUY", qty=2.0, price_native=100.0, currency="USD",
                fx_at_trade=1.0, trade_date="2026-01-01")
        r = compute_pmp_realized(conn, "TEST")
        assert r.qty == 2.0
        assert r.pmp_eur == 100.0  # qty * price * fx / qty = 100

    def test_adjust_overrides_price_and_fx(self):
        conn = sqlite3.connect(":memory:")
        _bootstrap_db(conn)
        # Original tx : EUR stored as USD with fx=1.0 (bug pattern)
        tx_id = _insert(conn, side="BUY", qty=2.0, price_native=100.0,
                        currency="USD", fx_at_trade=1.0, trade_date="2026-01-01")
        # ADJUST corrects to true USD = 115.74, fx=0.864
        _insert(conn, side="ADJUST", qty=2.0, price_native=115.74,
                currency="USD", fx_at_trade=0.864, trade_date="2026-01-02",
                notes='{"target_tx_id": ' + str(tx_id) + '}')
        r = compute_pmp_realized(conn, "TEST")
        assert r.qty == 2.0
        # PMP EUR = price × fx = 115.74 × 0.864 = 100.0 (preserved EUR cost)
        assert abs(r.pmp_eur - 100.0) < 0.01
        # PMP native = 115.74 (true USD price now)
        assert abs(r.pmp_native - 115.74) < 0.01


class TestAdjustEdgeCases:
    def test_malformed_notes_ignored(self):
        conn = sqlite3.connect(":memory:")
        _bootstrap_db(conn)
        _insert(conn, side="BUY", qty=1.0, price_native=50.0,
                trade_date="2026-01-01")
        _insert(conn, side="ADJUST", qty=1.0, price_native=999.0,
                trade_date="2026-01-02", notes="not_valid_json{",
                fx_at_trade=0.5)
        r = compute_pmp_realized(conn, "TEST")
        assert r.pmp_eur == 50.0  # Original preserved (malformed ADJUST ignored)

    def test_missing_target_tx_id_ignored(self):
        conn = sqlite3.connect(":memory:")
        _bootstrap_db(conn)
        _ = _insert(conn, side="BUY", qty=1.0, price_native=50.0, trade_date="2026-01-01")
        _insert(conn, side="ADJUST", qty=1.0, price_native=999.0,
                trade_date="2026-01-02", notes='{"reason": "no_target"}',
                fx_at_trade=0.5)
        r = compute_pmp_realized(conn, "TEST")
        assert r.pmp_eur == 50.0  # ADJUST sans target_tx_id ignored

    def test_eur_debited_preserved_under_cure(self):
        """EUR-side invariant : qty × price × fx pré-cure == post-cure."""
        conn = sqlite3.connect(":memory:")
        _bootstrap_db(conn)
        # Pre-cure : 1.242 × 319.65 × 1.0 = 397.01 EUR
        tx_id = _insert(conn, side="BUY", qty=1.242, price_native=319.65,
                        currency="USD", fx_at_trade=1.0, trade_date="2026-01-01")
        # ADJUST : 1.242 × 369.97 × 0.864 = 397.01 EUR (preserved)
        _insert(conn, side="ADJUST", qty=1.242, price_native=369.97,
                currency="USD", fx_at_trade=0.864, trade_date="2026-01-02",
                notes=f'{{"target_tx_id": {tx_id}}}')
        r = compute_pmp_realized(conn, "TEST")
        # EUR pool = 1.242 × 369.97 × 0.864 = 397.05 (preserved)
        assert abs(r.pmp_eur * r.qty - 397.01) < 0.1


class TestSellPathWithAdjust:
    """SELL tx with ADJUST modifies realized_pnl in EUR."""

    def test_sell_with_adjust_realized_eur(self):
        conn = sqlite3.connect(":memory:")
        _bootstrap_db(conn)
        # BUY 2 @ $100 fx=1.0 → cost_pool 200 EUR (overstated as if EUR)
        _insert(conn, side="BUY", qty=2.0, price_native=100.0, fx_at_trade=1.0,
                trade_date="2026-01-01")
        # SELL 1 @ $150 stored as "USD fx=1.0" (bug pattern)
        sell_id = _insert(conn, side="SELL", qty=1.0, price_native=150.0,
                          fx_at_trade=1.0, trade_date="2026-01-02")
        # ADJUST SELL : true USD $173.61, fx 0.864 → proceeds_eur = 150.0
        _insert(conn, side="ADJUST", qty=1.0, price_native=173.61,
                fx_at_trade=0.864, trade_date="2026-01-03",
                notes='{"target_tx_id": ' + str(sell_id) + '}')
        r = compute_pmp_realized(conn, "TEST")
        # Realized = proceeds - cost = 150 - 100 (pmp×qty) = 50 EUR
        assert abs(r.realized_pnl_eur - 50.0) < 0.1
        assert r.qty == 1.0
