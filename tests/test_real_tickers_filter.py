"""Tests #3 — filtre canonique real-tickers (L27).

Cf shared/book.py docstring + red-team Olivier 09/06.

Garde structurelle contre la landmine 'realized fantôme dans le ledger
immuable' : les agrégats production doivent appeler `is_test_ticker()` ou
utiliser `EXCLUDE_TEST_TICKERS_SQL`.
"""
from __future__ import annotations

import sqlite3

import pytest

from shared.book import (
    EXCLUDE_TEST_TICKERS_SQL,
    TEST_TICKER_PREFIXES,
    is_test_ticker,
)

# ============================================================================
# 1. is_test_ticker() — couverture par préfixe
# ============================================================================


@pytest.mark.parametrize("ticker", [
    "SMOKE126", "SMK126_1780976099", "TESTV", "FAKESKH", "FAKESKH_FEE",
    "WAVG", "DUP", "BAD", "MANUAL_DUP", "ANCHOR_TEST",
    "smoke126",      # lowercase
    "smk_other",     # lowercase variant
    "Test_X",        # mixed case
])
def test_is_test_ticker_returns_true_on_test_artifacts(ticker):
    assert is_test_ticker(ticker) is True, f"{ticker} devrait être détecté comme test"


@pytest.mark.parametrize("ticker", [
    # Tickers réels du book Olivier (vérifié broker_positions.yaml 09/06)
    "000660.KS", "4063.T", "6857.T", "6920.T", "7011.T",
    "ALAB", "AMD", "AMZN", "ASML.AS", "AVGO", "BESI.AS", "CCJ", "COHR",
    "ENTG", "GOOGL", "HO.PA", "KLAC", "LNG", "MP", "MU",
    "SAF.PA", "SNPS", "STMPA.PA", "SU.PA", "TSLA", "TSM",
])
def test_is_test_ticker_returns_false_on_real_tickers(ticker):
    assert is_test_ticker(ticker) is False, f"{ticker} ne devrait PAS être détecté test"


def test_is_test_ticker_handles_empty_and_none():
    assert is_test_ticker("") is False
    assert is_test_ticker(None) is False


# ============================================================================
# 2. EXCLUDE_TEST_TICKERS_SQL — filtre SQL canonique
# ============================================================================


def test_sql_clause_excludes_test_tickers_in_aggregate():
    """L'agrégat SUM(realized) avec EXCLUDE_TEST_TICKERS_SQL exclut les tickers test."""
    cx = sqlite3.connect(":memory:")
    cx.executescript("""
        CREATE TABLE positions_legacy (ticker TEXT, realized_pnl REAL);
        INSERT INTO positions_legacy VALUES
            ('000660.KS', 97.17),  -- réel : compte
            ('ALAB',     228.49),   -- réel : compte
            ('SMOKE126',  86.69),   -- fantôme : exclu
            ('SMK126_X', 100.00),   -- fantôme : exclu
            ('FAKESKH',   42.00);   -- fantôme : exclu
    """)
    cx.commit()

    # Sans filtre : total pollué
    total_polluted = cx.execute(
        "SELECT SUM(realized_pnl) FROM positions_legacy"
    ).fetchone()[0]
    assert total_polluted == pytest.approx(554.35, abs=0.01)

    # Avec filtre canonique : seuls les réels comptés
    total_real = cx.execute(
        f"SELECT SUM(realized_pnl) FROM positions_legacy WHERE {EXCLUDE_TEST_TICKERS_SQL}"
    ).fetchone()[0]
    assert total_real == pytest.approx(325.66, abs=0.01)  # 97.17 + 228.49

    # Différence = exactement la pollution
    assert total_polluted - total_real == pytest.approx(228.69, abs=0.01)
    # = 86.69 + 100 + 42


# ============================================================================
# 3. Cohérence : helper Python ≡ filtre SQL
# ============================================================================


def test_python_helper_and_sql_clause_agree(tmp_path):
    """L'enclos Python is_test_ticker et la clause SQL filtrent la MÊME chose.

    Garde structurelle : si quelqu'un ajoute un préfixe en Python sans le
    mettre dans la SQL clause (ou inverse), ce test l'attrape.
    """
    candidates = [
        "000660.KS", "ALAB", "MU",     # réels
        "SMOKE_X", "SMK_Y", "TEST_Z",  # tests
        "FAKEY", "DUP_X", "BAD_TK",    # tests
        "AAPL", "MSFT", "BTC",         # réels (non-book mais non-test)
    ]
    cx = sqlite3.connect(":memory:")
    cx.execute("CREATE TABLE t (ticker TEXT)")
    cx.executemany("INSERT INTO t VALUES (?)", [(c,) for c in candidates])
    cx.commit()

    excluded_by_sql = {
        r[0] for r in cx.execute(f"SELECT ticker FROM t WHERE NOT {EXCLUDE_TEST_TICKERS_SQL}")
    }
    excluded_by_py = {c for c in candidates if is_test_ticker(c)}

    assert excluded_by_sql == excluded_by_py, (
        f"Désaccord helper vs SQL : "
        f"py-only={excluded_by_py - excluded_by_sql}, "
        f"sql-only={excluded_by_sql - excluded_by_py}"
    )


# ============================================================================
# 4. Constants integrity
# ============================================================================


def test_prefixes_not_empty_and_not_too_broad():
    """Sanity : les préfixes filtrent quelque chose mais pas tout."""
    assert len(TEST_TICKER_PREFIXES) >= 4
    assert all(len(p) >= 3 for p in TEST_TICKER_PREFIXES), \
        "Préfixes <3 chars risquent collisions avec vrais tickers (ex: 'A' = AAPL/AMD)"


def test_real_book_tickers_immune():
    """REGRESSION GATE : tous les tickers du book Olivier sont immunes du filtre.

    Si un futur ajout au filtre attrape par erreur un vrai ticker, ce test
    rouge → revoir le préfixe avant ship.
    """
    REAL_BOOK_TICKERS = [
        "000660.KS", "4063.T", "6857.T", "6920.T", "7011.T",
        "ALAB", "AMD", "AMZN", "ASML.AS", "AVGO", "BESI.AS", "CCJ", "COHR",
        "ENTG", "GOOGL", "HO.PA", "KLAC", "LNG", "MP", "MU",
        "SAF.PA", "SNPS", "STMPA.PA", "SU.PA", "TSLA", "TSM",
    ]
    caught = [tk for tk in REAL_BOOK_TICKERS if is_test_ticker(tk)]
    assert not caught, (
        f"Le filtre attrape des vrais tickers : {caught}. "
        f"Revoir TEST_TICKER_PREFIXES dans shared/book.py."
    )
