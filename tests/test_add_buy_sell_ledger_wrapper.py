"""Tests #126 — add_buy/add_sell wrappers INSERT transactions.

Vérifie que les wrappers :
  1. INSERT dans transactions (pas UPDATE positions qui est une VUE)
  2. Préservent les side effects (auto_classify_new_ticker, lock_in_detector)
  3. Maintiennent les invariants de la VUE (qty, PRU pondéré, realized_pnl)
  4. Sont idempotents via broker_trade_id UNIQUE
  5. Valident qty oversell, qty/price > 0
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def ledger_db_with_view(monkeypatch, tmp_path):
    """In-memory SQLite : schema 0046 + VIEW positions (équivalent 0048)."""
    db_path = tmp_path / "test_ledger.db"
    cx = sqlite3.connect(str(db_path))
    cx.row_factory = sqlite3.Row

    # Schema 0046
    cx.executescript("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, side TEXT NOT NULL,
            qty REAL NOT NULL CHECK(qty > 0),
            price_native REAL NOT NULL, fees_native REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL, fx_at_trade REAL NOT NULL,
            fx_is_derived INTEGER NOT NULL DEFAULT 0,
            trade_date TEXT NOT NULL, broker_trade_id TEXT UNIQUE,
            source TEXT NOT NULL, is_anchor INTEGER NOT NULL DEFAULT 0,
            notes TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE positions_meta (
            ticker TEXT PRIMARY KEY, notes TEXT, status TEXT, account TEXT, wrapper TEXT
        );
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, asof TEXT,
            price_native REAL, currency TEXT, source TEXT
        );
        CREATE TABLE fx_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, base TEXT, quote TEXT,
            rate REAL, asof TEXT, source TEXT
        );
        CREATE INDEX idx_px_ticker_asof ON price_history(ticker, asof DESC);
        CREATE INDEX idx_fx_pair_asof ON fx_history(base, quote, asof DESC);
        CREATE VIEW positions AS
        WITH buys AS (
            SELECT ticker, MIN(trade_date) AS opened_at,
                   SUM(qty * price_native + fees_native) / SUM(qty) AS pru_native,
                   SUM(qty * price_native * fx_at_trade + fees_native * fx_at_trade) / SUM(qty) AS pru_eur,
                   SUM(qty) AS qty_buy
            FROM transactions WHERE side='BUY' GROUP BY ticker
        ),
        sells AS (
            SELECT s.ticker, SUM(s.qty) AS qty_sell,
                   SUM(s.qty * s.price_native * s.fx_at_trade - s.fees_native * s.fx_at_trade
                       - s.qty * (
                         SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade) / SUM(b.qty)
                         FROM transactions b
                         WHERE b.ticker = s.ticker AND b.side = 'BUY' AND b.trade_date < s.trade_date
                       )) AS realized_pnl_eur
            FROM transactions s WHERE s.side='SELL' GROUP BY s.ticker
        )
        SELECT m.rowid AS id, m.ticker,
               COALESCE(b.qty_buy, 0) - COALESCE(s.qty_sell, 0) AS qty,
               b.pru_eur AS avg_cost, b.pru_eur AS avg_cost_eur, b.pru_native AS avg_cost_native,
               'EUR' AS avg_cost_currency, b.pru_eur AS avg_cost_value,
               b.opened_at AS avg_cost_asof, 1.0 AS fx_at_purchase,
               COALESCE(s.realized_pnl_eur, 0) AS realized_pnl,
               b.opened_at, b.opened_at AS last_updated,
               m.notes, m.status, m.account, m.wrapper
        FROM positions_meta m
        LEFT JOIN buys b USING(ticker)
        LEFT JOIN sells s USING(ticker);
    """)
    cx.commit()

    # Monkey-patch shared.storage.db pour pointer vers cette DB
    from contextlib import contextmanager
    @contextmanager
    def fake_db():
        nx = sqlite3.connect(str(db_path))
        nx.row_factory = sqlite3.Row
        try:
            yield nx
        finally:
            nx.close()

    monkeypatch.setattr("shared.storage.db", fake_db)
    monkeypatch.setattr("shared.positions.db", fake_db)

    yield cx
    cx.close()


def _no_classify(monkeypatch):
    """Stub auto_classify et lock_in_detector pour tests isolés."""
    monkeypatch.setattr("shared.positions._auto_classify_new_ticker", lambda tk: None)


# ============================================================================
# 1. add_buy : INSERT transactions + qty/avg via VUE
# ============================================================================


def test_add_buy_inserts_transaction_BUY(ledger_db_with_view, monkeypatch):
    _no_classify(monkeypatch)
    from shared.positions import add_buy

    r = add_buy("TESTEUR", qty=10.0, price=100.0, currency="EUR",
                fx_at_trade=1.0, broker_trade_id="T1", source="test")
    assert r["qty"] == 10.0
    assert r["avg_cost_eur"] == pytest.approx(100.0, abs=1e-6)
    assert r["realized_pnl"] == 0

    # Vérifie que la transaction est bien dans le ledger (pas dans positions)
    cx = ledger_db_with_view
    n = cx.execute("SELECT COUNT(*) FROM transactions WHERE ticker='TESTEUR'").fetchone()[0]
    assert n == 1
    side = cx.execute("SELECT side FROM transactions WHERE ticker='TESTEUR'").fetchone()[0]
    assert side == "BUY"


def test_add_buy_weighted_avg_via_view(ledger_db_with_view, monkeypatch):
    """2 BUYs successifs : avg pondéré dans VUE = (q1*p1 + q2*p2) / (q1+q2)."""
    _no_classify(monkeypatch)
    from shared.positions import add_buy

    add_buy("WAVG", qty=10.0, price=100.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="W1", source="test")
    r = add_buy("WAVG", qty=10.0, price=120.0, currency="EUR", fx_at_trade=1.0,
                broker_trade_id="W2", source="test")
    assert r["qty"] == 20.0
    assert r["avg_cost_eur"] == pytest.approx(110.0, abs=1e-6)


def test_add_buy_auto_classify_only_on_first(ledger_db_with_view, monkeypatch):
    """auto_classify_new_ticker appelé sur 1er BUY uniquement (was_new_entry)."""
    from shared.positions import add_buy
    calls = []
    monkeypatch.setattr("shared.positions._auto_classify_new_ticker",
                       lambda tk: calls.append(tk))

    add_buy("CLASSIFY", qty=1.0, price=10.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="C1", source="test")
    assert calls == ["CLASSIFY"]

    add_buy("CLASSIFY", qty=1.0, price=20.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="C2", source="test")
    assert calls == ["CLASSIFY"]  # Pas re-classifié


def test_add_buy_idempotence_via_broker_trade_id(ledger_db_with_view, monkeypatch):
    """Duplicate broker_trade_id → IntegrityError UNIQUE constraint."""
    _no_classify(monkeypatch)
    from shared.positions import add_buy

    add_buy("DUP", qty=1.0, price=10.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="DUP-1", source="test")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        add_buy("DUP", qty=99.0, price=99.0, currency="EUR", fx_at_trade=1.0,
                broker_trade_id="DUP-1", source="test_duplicate")


def test_add_buy_validates_positive_qty_price(ledger_db_with_view, monkeypatch):
    _no_classify(monkeypatch)
    from shared.positions import add_buy

    with pytest.raises(ValueError, match="must be positive"):
        add_buy("BAD", qty=-1.0, price=10.0, currency="EUR", fx_at_trade=1.0)
    with pytest.raises(ValueError, match="must be positive"):
        add_buy("BAD", qty=1.0, price=0.0, currency="EUR", fx_at_trade=1.0)


# ============================================================================
# 2. add_sell : INSERT SELL + lock_in_detector hook + realized via VUE
# ============================================================================


def test_add_sell_inserts_transaction_SELL(ledger_db_with_view, monkeypatch):
    _no_classify(monkeypatch)
    monkeypatch.setattr("intelligence.lock_in_detector.detect_winner_sell",
                       lambda **kwargs: None)
    from shared.positions import add_buy, add_sell

    add_buy("SELLTEST", qty=20.0, price=110.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="ST-B1", source="test")
    r = add_sell("SELLTEST", qty=5.0, price=130.0, currency="EUR", fx_at_trade=1.0,
                 broker_trade_id="ST-S1", source="test")
    assert r["sold_qty"] == 5.0
    assert r["realized_pnl_event"] == pytest.approx(100.0, abs=1e-6)  # 5*(130-110)
    assert r["remaining_qty"] == 15.0
    assert r["closed"] is False


def test_add_sell_validates_qty_oversell(ledger_db_with_view, monkeypatch):
    _no_classify(monkeypatch)
    from shared.positions import add_buy, add_sell

    add_buy("OVER", qty=5.0, price=10.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="OV-B1", source="test")
    with pytest.raises(ValueError, match="> position qty"):
        add_sell("OVER", qty=99.0, price=10.0, currency="EUR", fx_at_trade=1.0)


def test_add_sell_lock_in_hook_called(ledger_db_with_view, monkeypatch):
    """L1 v2.c.6 : hook lock_in_detector.detect_winner_sell appelé post-INSERT."""
    _no_classify(monkeypatch)
    from shared.positions import add_buy, add_sell

    hook_calls = []
    def fake_hook(**kwargs):
        hook_calls.append(kwargs)

    monkeypatch.setattr("intelligence.lock_in_detector.detect_winner_sell", fake_hook)

    add_buy("HOOK", qty=10.0, price=100.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="H-B1", source="test")
    add_sell("HOOK", qty=3.0, price=130.0, currency="EUR", fx_at_trade=1.0,
             broker_trade_id="H-S1", source="test")

    assert len(hook_calls) == 1
    h = hook_calls[0]
    assert h["ticker"] == "HOOK"
    assert h["qty_sold"] == 3.0
    assert h["sold_price_native"] == 130.0
    assert h["qty_before"] == 10.0


def test_add_sell_hook_silent_miss_dont_break_sell(ledger_db_with_view, monkeypatch):
    """L7 silent miss : si hook crash, la vente reste valide."""
    _no_classify(monkeypatch)

    def crashing_hook(**kwargs):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr("intelligence.lock_in_detector.detect_winner_sell", crashing_hook)

    from shared.positions import add_buy, add_sell
    add_buy("CRASH", qty=10.0, price=100.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="CR-B1", source="test")
    # Doit pas lever malgré le hook qui crash
    r = add_sell("CRASH", qty=3.0, price=130.0, currency="EUR", fx_at_trade=1.0,
                 broker_trade_id="CR-S1", source="test")
    assert r["remaining_qty"] == 7.0  # vente bien comptée


def test_add_sell_no_open_position_raises(ledger_db_with_view, monkeypatch):
    _no_classify(monkeypatch)
    from shared.positions import add_sell

    with pytest.raises(ValueError, match="No open position"):
        add_sell("NOPOS", qty=1.0, price=10.0, currency="EUR", fx_at_trade=1.0)


# ============================================================================
# 3. Bout-à-bout : add_buy + add_sell cohérent avec ground truth réplique #121
# ============================================================================


def test_e2e_replay_sk_hynix_pattern(ledger_db_with_view, monkeypatch):
    """Reproduit le pattern SK Hynix #121 (BUY puis SELL partielle) — vérifie
    que add_buy + add_sell donnent qty et realized cohérents."""
    _no_classify(monkeypatch)
    monkeypatch.setattr("intelligence.lock_in_detector.detect_winner_sell",
                       lambda **kwargs: None)
    from shared.positions import add_buy, add_sell, get_position

    # SK Hynix réel : buy 1.886792@1060, sell 0.371212@1325, reste 1.515580
    add_buy("FAKESKH", qty=1.886792, price=1060.0, currency="EUR", fx_at_trade=1.0,
            broker_trade_id="SKH-B1", source="test", trade_date="2026-05-15T17:56")
    add_sell("FAKESKH", qty=0.371212, price=1325.0, currency="EUR", fx_at_trade=1.0,
             broker_trade_id="SKH-S1", source="test", trade_date="2026-05-29T14:55")

    pos = get_position("FAKESKH")
    assert pos["qty"] == pytest.approx(1.515580, abs=1e-6)
    assert pos["avg_cost_eur"] == pytest.approx(1060.0, abs=0.01)
    # realized = 0.371212 * (1325 - 1060) = 98.3712  (pas de fees ici)
    assert pos["realized_pnl"] == pytest.approx(98.3712, abs=0.01)
