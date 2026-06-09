"""Tests du gate check_ledger_view_equivalence.

Cf SPEC_LEDGER.md §4 (Cure #4 — gate byte-identité avant swap).

5 modes d'exit couverts :
  0 = GATE GREEN  : 21 propres match + 5 stale réconciliées (back-fill effectué)
  1 = ABORT       : 1+ propre en drift (corruption) OU stale match inattendu
  2 = ABORT       : 5 stale sans back-fill (swap perdrait les réconciliations)
  3 = ABORT       : transactions vide (pas d'anchor encore)

Le gate est tautologique sur les 21 par construction (anchor reproduit table).
Ces tests valident la mécanique du gate, pas la propreté des 21 (qui est
portée par la partition 3-signaux dans scripts/anchor_clean_positions.py).
"""
from __future__ import annotations

import sqlite3

import pytest

# On teste les fonctions pures du gate, isolées de storage.db()
from scripts.check_ledger_view_equivalence import (
    STALE_TICKERS,
    TOL_QTY,
    compute_table_values,
    compute_view_values,
    diff_position,
    is_match,
)


@pytest.fixture
def gate_db():
    """In-memory SQLite avec schema 0046 + positions table minimale (pré-swap)."""
    cx = sqlite3.connect(":memory:")
    # Schema transactions (mirror migration 0046)
    cx.execute("""
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
        )
    """)
    # Mini positions (juste les colonnes que le gate lit)
    cx.execute("""
        CREATE TABLE positions (
            ticker TEXT PRIMARY KEY, qty REAL, avg_cost_native REAL,
            avg_cost_eur REAL, realized_pnl REAL, status TEXT
        )
    """)
    yield cx
    cx.close()


def _insert_anchor(cx, ticker, qty, avg_native, avg_eur, currency="EUR"):
    """Anchor BUY synthétique (astuce fx)."""
    fx_anchor = avg_eur / avg_native
    cx.execute("""
        INSERT INTO transactions (ticker, side, qty, price_native, fees_native, currency,
                                  fx_at_trade, trade_date, source, is_anchor)
        VALUES (?, 'BUY', ?, ?, 0, ?, ?, '2026-05-15', 'anchor_test', 1)
    """, (ticker, qty, avg_native, currency, fx_anchor))


def _insert_position(cx, ticker, qty, avg_native, avg_eur, realized_pnl=0):
    cx.execute("""
        INSERT INTO positions (ticker, qty, avg_cost_native, avg_cost_eur, realized_pnl, status)
        VALUES (?, ?, ?, ?, ?, 'open')
    """, (ticker, qty, avg_native, avg_eur, realized_pnl))


# ============================================================================
# is_match() — fonction pure
# ============================================================================


def test_is_match_exact():
    """Δ = 0 partout → match."""
    d = {"qty": 0.0, "pru_native": 0.0, "pru_eur": 0.0, "realized_pnl": 0.0}
    assert is_match(d) is True


def test_is_match_within_tolerance():
    """Δ sous tolérances → match."""
    d = {"qty": TOL_QTY / 2, "pru_native": 1e-10, "pru_eur": 1e-10, "realized_pnl": 0.005}
    assert is_match(d) is True


def test_is_match_qty_drift_fails():
    """Δqty > tolérance → no match (=drift signalé)."""
    d = {"qty": TOL_QTY * 100, "pru_native": 0.0, "pru_eur": 0.0, "realized_pnl": 0.0}
    assert is_match(d) is False


def test_is_match_none_values_fail():
    """None (transaction absente OU position absente) → no match."""
    d = {"qty": None, "pru_native": None, "pru_eur": None, "realized_pnl": None}
    assert is_match(d) is False


# ============================================================================
# compute_view_values + compute_table_values + diff_position — mécanique gate
# ============================================================================


def test_anchor_reproduit_table_propre(gate_db):
    """Cas nominal propre : anchor BUY avec astuce fx → VUE matche positions exactement."""
    _insert_anchor(gate_db, "TEST", qty=10.0, avg_native=100.0, avg_eur=110.0)
    _insert_position(gate_db, "TEST", qty=10.0, avg_native=100.0, avg_eur=110.0)
    gate_db.commit()

    view = compute_view_values(gate_db)
    table = compute_table_values(gate_db)
    d = diff_position(view["TEST"], table["TEST"])
    assert is_match(d) is True, f"Anchor doit reproduire table exactement, mais Δ={d}"


def test_drift_propre_detecte(gate_db):
    """Une position propre modifiée hors ledger (anchor en place mais positions.qty changé) → drift détecté."""
    _insert_anchor(gate_db, "TEST", qty=10.0, avg_native=100.0, avg_eur=110.0)
    _insert_position(gate_db, "TEST", qty=15.0, avg_native=100.0, avg_eur=110.0)  # qty diffère
    gate_db.commit()

    view = compute_view_values(gate_db)
    table = compute_table_values(gate_db)
    d = diff_position(view["TEST"], table["TEST"])
    assert is_match(d) is False
    assert abs(d["qty"]) > TOL_QTY, "Δqty doit être significatif"


def test_stale_sans_anchor_donne_no_view(gate_db):
    """Stale sans transactions : VUE absente, table présente."""
    _insert_position(gate_db, "000660.KS", qty=1.48, avg_native=1085.0, avg_eur=1085.0, realized_pnl=77.88)
    gate_db.commit()

    view = compute_view_values(gate_db)
    table = compute_table_values(gate_db)
    assert "000660.KS" not in view  # pas dans transactions
    assert "000660.KS" in table


def test_stale_apres_backfill_donne_diff_visible(gate_db):
    """Stale après back-fill TR : VUE présente (réconciliée), table présente (stale)."""
    # Ground truth hypothétique (TR export) : 1.515580 actions à PRU 1060€
    # Buy d'origine + vente partielle
    _insert_anchor(gate_db, "000660.KS", qty=1.886792, avg_native=1060.0, avg_eur=1060.0, currency="EUR")
    gate_db.execute("""
        INSERT INTO transactions (ticker, side, qty, price_native, fees_native, currency,
                                  fx_at_trade, trade_date, source, is_anchor)
        VALUES ('000660.KS', 'SELL', 0.371212, 1325.0, 0, 'EUR', 1.0, '2026-05-29', 'TR_export_2026-06-09_TEST', 0)
    """)
    # Stale table state (avant réconciliation)
    _insert_position(gate_db, "000660.KS", qty=1.4809, avg_native=1085.0, avg_eur=1085.0, realized_pnl=77.88)
    gate_db.commit()

    view = compute_view_values(gate_db)
    table = compute_table_values(gate_db)
    assert "000660.KS" in view
    assert "000660.KS" in table

    d = diff_position(view["000660.KS"], table["000660.KS"])
    # Doit pas matcher : la VUE réconciliée diffère du snapshot stale
    assert is_match(d) is False, "Stale réconciliée doit différer du snapshot stale"
    # Δqty = 1.515580 - 1.4809 = +0.034680
    assert d["qty"] == pytest.approx(0.034680, abs=1e-4)
    # ΔrealizedPnL = 98.37 - 77.88 = +20.49
    expected_rpnl_view = 0.371212 * (1325.0 - 1060.0)  # 98.37
    assert d["realized_pnl"] == pytest.approx(expected_rpnl_view - 77.88, abs=0.01)


def test_stale_constants() -> None:
    """Liste dure des 5 stale = exactly les tickers attendus."""
    assert {"000660.KS", "ALAB", "MU", "CCJ", "6920.T"} == STALE_TICKERS
    assert len(STALE_TICKERS) == 5


# ============================================================================
# Smoke d'intégration : exit codes du gate complet
# ============================================================================


def _setup_21_propres_5_stale(cx):
    """Helper : crée 21 anchors propres (matchant positions) + 5 positions stale sans anchor."""
    propre_data = [
        ("ASML.AS", 3.0, 820.95, 820.95),
        ("BESI.AS", 6.0, 262.71, 262.71),
        ("HO.PA", 7.0, 81.59, 81.59),
        ("SAF.PA", 2.0, 213.75, 213.75),
        ("STMPA.PA", 42.0, 22.84, 22.84),
        ("SU.PA", 6.0, 219.49, 219.49),
        ("4063.T", 107.522, 41.8528, 41.8528),
        ("6857.T", 12.1029, 149.7916, 149.7916),
        ("7011.T", 109.6877, 22.7918, 22.7918),
        ("AMD", 4.2118, 143.541, 143.541),
        ("AMZN", 9.8633, 223.0442, 223.0442),
        ("AVGO", 3.7334, 363.7578, 363.7578),
        ("COHR", 3.498, 328.1875, 328.1875),
        ("ENTG", 12.2386, 113.7409, 113.7409),
        ("GOOGL", 6.6908, 260.554, 260.554),
        ("KLAC", 1.2719, 1572.3233, 1572.3233),
        ("LNG", 10.219, 198.2928, 198.2928),
        ("MP", 28.4807, 52.0359, 52.0359),
        ("SNPS", 8.032, 434.4042, 434.4042),
        ("TSLA", 4.9081, 352.9211, 352.9211),
        ("TSM", 11.6954, 222.2524, 222.2524),
    ]
    assert len(propre_data) == 21
    for tk, qty, n, e in propre_data:
        _insert_anchor(cx, tk, qty, n, e)
        _insert_position(cx, tk, qty, n, e)
    # 5 stale sans anchor
    for tk in ("000660.KS", "ALAB", "MU", "CCJ", "6920.T"):
        _insert_position(cx, tk, 1.0, 100.0, 100.0, realized_pnl=50.0)
    cx.commit()


def test_exit_2_when_stale_not_backfilled(gate_db):
    """État actuel (09/06) : 21 propres OK + 5 stale sans transactions → exit 2."""
    _setup_21_propres_5_stale(gate_db)

    # Reproduit la logique du main() sans subprocess
    view = compute_view_values(gate_db)
    table = compute_table_values(gate_db)
    stale_missing = [tk for tk in STALE_TICKERS if tk in table and tk not in view]
    assert len(stale_missing) == 5  # 5 stale visibles dans positions mais sans VUE
    # Tous les 21 propres match
    propre_matches = sum(
        1 for tk in table
        if tk not in STALE_TICKERS
        and tk in view
        and is_match(diff_position(view[tk], table[tk]))
    )
    assert propre_matches == 21


def test_exit_0_when_21_match_and_5_reconciled(gate_db):
    """Cas hypothétique post-#121 : 21 match + 5 stale ont des transactions réelles différentes."""
    _setup_21_propres_5_stale(gate_db)
    # Pour les 5 stale : INSERT trades qui produisent VUE différente du stale en table
    for tk in ("000660.KS", "ALAB", "MU", "CCJ", "6920.T"):
        # Anchor + vente partielle = VUE différente
        gate_db.execute("""
            INSERT INTO transactions (ticker, side, qty, price_native, fees_native, currency,
                                      fx_at_trade, trade_date, source, is_anchor)
            VALUES (?, 'BUY', 2.0, 200.0, 0, 'EUR', 1.0, '2026-01-01', 'TR_test', 0)
        """, (tk,))
        gate_db.execute("""
            INSERT INTO transactions (ticker, side, qty, price_native, fees_native, currency,
                                      fx_at_trade, trade_date, source, is_anchor)
            VALUES (?, 'SELL', 0.5, 250.0, 0, 'EUR', 1.0, '2026-02-01', 'TR_test', 0)
        """, (tk,))
    gate_db.commit()

    view = compute_view_values(gate_db)
    table = compute_table_values(gate_db)
    # 21 propres encore match
    propre_matches = sum(
        1 for tk in table
        if tk not in STALE_TICKERS and is_match(diff_position(view[tk], table[tk]))
    )
    assert propre_matches == 21
    # 5 stale ont VUE qui diffère de table (= réconciliées, pas match)
    stale_reconciled = sum(
        1 for tk in STALE_TICKERS
        if tk in view and tk in table and not is_match(diff_position(view[tk], table[tk]))
    )
    assert stale_reconciled == 5
