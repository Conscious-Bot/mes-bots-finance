"""Tests verrouillants SPEC_LEDGER.md §7 — les 5 invariants porteurs du ledger.

Couvre les 5 invariants qui rendent la classe "broker import met à jour qty
sans recalcul cost basis" structurellement impossible :

  1. Append-only structurel : UPDATE → RAISE, DELETE → RAISE.
  2. Idempotence structurelle : broker_trade_id UNIQUE (re-INSERT → reject DB).
  3. qty > 0 strict : signe porté par side, jamais par qty.
  4. fx_at_trade NOT NULL : aucun trade sans fx (EUR : fx=1.0).
  5. PRU temporellement ordonné : realized_pnl calculé sur PRU pré-vente,
     pas de leak de la vente dans son propre PRU.

Le test #1 (UPDATE/DELETE → RAISE) est LE veto structurel : il échoue si
jamais on essaie de patcher un trade à la main (ce qui rejouerait
exactement la maladie de la nuit 09/06 — store-derived-stale).
"""
from __future__ import annotations

import sqlite3

import pytest

# ============================================================================
# Fixture : schema 0046 fresh par test (in-memory SQLite)
# ============================================================================


@pytest.fixture
def ledger_db():
    """In-memory SQLite avec schema 0046 (transactions + positions_meta + 3 triggers)."""
    cx = sqlite3.connect(":memory:")
    cx.execute("""
        CREATE TABLE transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            side            TEXT NOT NULL,
            qty             REAL NOT NULL CHECK(qty > 0),
            price_native    REAL NOT NULL,
            fees_native     REAL NOT NULL DEFAULT 0,
            currency        TEXT NOT NULL,
            fx_at_trade     REAL NOT NULL,
            fx_is_derived   INTEGER NOT NULL DEFAULT 0 CHECK(fx_is_derived IN (0, 1)),
            trade_date      TEXT NOT NULL,
            broker_trade_id TEXT UNIQUE,
            source          TEXT NOT NULL,
            is_anchor       INTEGER NOT NULL DEFAULT 0 CHECK(is_anchor IN (0, 1)),
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cx.execute("CREATE INDEX idx_transactions_ticker_side_date ON transactions(ticker, side, trade_date)")
    cx.execute("""
        CREATE TRIGGER transactions_writeonce_update
        BEFORE UPDATE ON transactions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'transactions append-only : UPDATE interdit.');
        END
    """)
    cx.execute("""
        CREATE TRIGGER transactions_writeonce_delete
        BEFORE DELETE ON transactions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'transactions append-only : DELETE interdit.');
        END
    """)
    cx.execute("""
        CREATE TABLE positions_meta (
            ticker TEXT PRIMARY KEY, notes TEXT, status TEXT, account TEXT, wrapper TEXT
        )
    """)
    cx.commit()
    yield cx
    cx.close()


def _insert_trade(cx, **kwargs):
    """Helper : INSERT trade avec defaults sensés."""
    defaults = {
        "ticker": "TEST",
        "side": "BUY",
        "qty": 10.0,
        "price_native": 100.0,
        "fees_native": 0.0,
        "currency": "EUR",
        "fx_at_trade": 1.0,
        "fx_is_derived": 0,
        "trade_date": "2026-01-15",
        "broker_trade_id": None,
        "source": "test",
        "is_anchor": 0,
        "notes": None,
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    cx.execute(f"INSERT INTO transactions ({cols}) VALUES ({placeholders})", tuple(defaults.values()))


# ============================================================================
# 1. Append-only structurel (LE VETO contre store-derived-stale)
# ============================================================================


def test_update_qty_raises(ledger_db):
    """UPDATE qty d'une transaction => RAISE.

    C'est le veto qui rend impossible le pansement humain
    'qty_aligned_to_broker_2026-05-29' qui a contaminé SK Hynix.
    """
    _insert_trade(ledger_db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger_db.execute("UPDATE transactions SET qty = 99.0 WHERE id = 1")


def test_update_price_raises(ledger_db):
    """UPDATE price_native d'une transaction => RAISE."""
    _insert_trade(ledger_db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger_db.execute("UPDATE transactions SET price_native = 999.0 WHERE id = 1")


def test_update_any_column_raises(ledger_db):
    """UPDATE de n'importe quelle colonne (même notes "inoffensive") => RAISE.

    Le ledger est immuable au sens fort : aucune correction par edit.
    Corrections passent par entrée compensatoire (ADJUST futur).
    """
    _insert_trade(ledger_db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger_db.execute("UPDATE transactions SET notes = 'correction' WHERE id = 1")


def test_delete_raises(ledger_db):
    """DELETE d'une transaction => RAISE.

    Append-only au sens fort : on ne peut pas non plus supprimer
    "pour corriger". Sinon ce n'est pas immuable.
    """
    _insert_trade(ledger_db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger_db.execute("DELETE FROM transactions WHERE id = 1")


# ============================================================================
# 2. Idempotence structurelle (broker_trade_id UNIQUE)
# ============================================================================


def test_duplicate_broker_trade_id_raises(ledger_db):
    """INSERT du même broker_trade_id => UNIQUE constraint RAISE.

    C'est l'idempotence mécanique L27 : impossible d'ingérer 2x le même
    trade TR par accident. La DB rejette structurellement le doublon,
    pas une logique applicative oubliable.
    """
    _insert_trade(ledger_db, broker_trade_id="TR-12345")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _insert_trade(ledger_db, broker_trade_id="TR-12345", qty=99.0)


def test_null_broker_trade_id_allowed_multiple(ledger_db):
    """Plusieurs broker_trade_id=NULL acceptés (anchors et manual ont NULL).

    SQLite : UNIQUE permet plusieurs NULL. Confirmé pour notre cas usage
    (anchors back-fill + corrections manuelles documentées).
    """
    _insert_trade(ledger_db, broker_trade_id=None, source="anchor_2026-06-09", is_anchor=1)
    _insert_trade(ledger_db, broker_trade_id=None, source="manual_correction_2026-06-09")
    n = ledger_db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert n == 2


# ============================================================================
# 3. qty > 0 strict (signe porté par side, jamais par qty)
# ============================================================================


def test_negative_qty_raises(ledger_db):
    """INSERT qty < 0 => CHECK constraint RAISE."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert_trade(ledger_db, qty=-10.0)


def test_zero_qty_raises(ledger_db):
    """INSERT qty == 0 => CHECK constraint RAISE.

    qty=0 n'a aucun sens (BUY 0 unité = no-op qui pollue le ledger).
    """
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert_trade(ledger_db, qty=0.0)


# ============================================================================
# 4. fx_at_trade NOT NULL (aucun trade sans fx, même EUR = 1.0 explicite)
# ============================================================================


def test_null_fx_raises(ledger_db):
    """fx_at_trade NULL => NOT NULL constraint RAISE.

    Même un trade EUR doit avoir fx_at_trade=1.0 explicite.
    Pas de fallback silencieux qui dériverait dans le temps.
    """
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        _insert_trade(ledger_db, fx_at_trade=None)


def test_eur_trade_requires_explicit_fx_1(ledger_db):
    """EUR trade avec fx_at_trade=1.0 explicite => OK, ne crashe pas."""
    _insert_trade(ledger_db, currency="EUR", fx_at_trade=1.0)
    row = ledger_db.execute("SELECT currency, fx_at_trade FROM transactions").fetchone()
    assert row == ("EUR", 1.0)


# ============================================================================
# 5. PRU temporellement ordonné (sous-requête corrélée — pas de leak vente)
# ============================================================================


def test_pru_simple_weighted_average(ledger_db):
    """Fixture 2 BUY (100@10 + 100@20) → PRU pondéré = 15.0 exact.

    Confirme que la formule SPEC §2.2 (cost / qty pondéré) est correcte.
    """
    _insert_trade(ledger_db, ticker="AAA", side="BUY", qty=100.0, price_native=10.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-01-01", broker_trade_id="T1")
    _insert_trade(ledger_db, ticker="AAA", side="BUY", qty=100.0, price_native=20.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-02-01", broker_trade_id="T2")
    ledger_db.commit()

    # Reproduit la formule de la VIEW (cf SPEC_LEDGER §2.2)
    row = ledger_db.execute("""
        SELECT SUM(qty * price_native + fees_native) / SUM(qty) AS pru_native,
               SUM(qty * price_native * fx_at_trade + fees_native * fx_at_trade) / SUM(qty) AS pru_eur
        FROM transactions
        WHERE ticker = 'AAA' AND side = 'BUY'
    """).fetchone()
    assert row[0] == pytest.approx(15.0, rel=1e-9)  # pru_native
    assert row[1] == pytest.approx(15.0, rel=1e-9)  # pru_eur (EUR currency, fx=1)


def test_realized_pnl_uses_pru_before_sell_not_after(ledger_db):
    """Le veto temporel : vente entre 2 BUY ne se mange pas dans son propre PRU.

    Scenario :
      - BUY  100 @ 10 EUR le 2026-01-01 → PRU = 10
      - SELL  50 @ 25 EUR le 2026-02-01 → realized_pnl = 50 x (25 - 10) = 750
      - BUY  100 @ 30 EUR le 2026-03-01 → PRU monte à (1000 + 3000) / 200 = 20
        MAIS ce 2e BUY est APRÈS la vente, donc NE DOIT PAS entrer dans
        le PRU au moment du calcul de realized_pnl.

    Si la sous-requête corrélée est buggée (oublie le WHERE trade_date < sell_date),
    realized_pnl serait calculé sur PRU=20 → 50 x (25 - 20) = 250. Faux.
    """
    _insert_trade(ledger_db, ticker="BBB", side="BUY", qty=100.0, price_native=10.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-01-01", broker_trade_id="B1")
    _insert_trade(ledger_db, ticker="BBB", side="SELL", qty=50.0, price_native=25.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-02-01", broker_trade_id="S1")
    _insert_trade(ledger_db, ticker="BBB", side="BUY", qty=100.0, price_native=30.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-03-01", broker_trade_id="B2")
    ledger_db.commit()

    # Reproduit la sous-requête corrélée de la VIEW pour realized_pnl (SPEC §2.2)
    row = ledger_db.execute("""
        SELECT SUM(
            s.qty * s.price_native * s.fx_at_trade
          - s.fees_native * s.fx_at_trade
          - s.qty * (
              SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade)
                   / SUM(b.qty)
              FROM transactions b
              WHERE b.ticker = s.ticker
                AND b.side = 'BUY'
                AND b.trade_date < s.trade_date
            )
        ) AS realized_pnl_eur
        FROM transactions s
        WHERE s.ticker = 'BBB' AND s.side = 'SELL'
    """).fetchone()
    # 50 x (25 - 10) = 750. PRU au moment de la vente = 10 (uniquement le 1er BUY),
    # le 2e BUY @ 30 (postérieur) ne contamine pas.
    assert row[0] == pytest.approx(750.0, rel=1e-9)


def test_realized_pnl_with_fees_capitalized_on_buy_deducted_on_sell(ledger_db):
    """Frais capitalisés au PRU côté BUY, déduits du proceeds côté SELL.

    Scenario (convention FR) :
      - BUY 100 @ 10 + fees 5 → cost = 1005, PRU = 1005/100 = 10.05
      - SELL 50 @ 25 + fees 3 → proceeds = 50x25 - 3 = 1247
                              realized_pnl = 1247 - 50 x 10.05 = 1247 - 502.5 = 744.5
    """
    _insert_trade(ledger_db, ticker="CCC", side="BUY", qty=100.0, price_native=10.0, fees_native=5.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-01-01", broker_trade_id="C1")
    _insert_trade(ledger_db, ticker="CCC", side="SELL", qty=50.0, price_native=25.0, fees_native=3.0,
                  currency="EUR", fx_at_trade=1.0, trade_date="2026-02-01", broker_trade_id="C2")
    ledger_db.commit()

    row = ledger_db.execute("""
        SELECT SUM(
            s.qty * s.price_native * s.fx_at_trade
          - s.fees_native * s.fx_at_trade
          - s.qty * (
              SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade)
                   / SUM(b.qty)
              FROM transactions b
              WHERE b.ticker = s.ticker
                AND b.side = 'BUY'
                AND b.trade_date < s.trade_date
            )
        )
        FROM transactions s
        WHERE s.ticker = 'CCC' AND s.side = 'SELL'
    """).fetchone()
    # 50x25 - 3 - 50x10.05 = 1250 - 3 - 502.5 = 744.5
    assert row[0] == pytest.approx(744.5, rel=1e-9)


# ============================================================================
# 6. Anchor astuce (SPEC §3.1 — fx_at_trade = avg_eur / avg_native reproduit les 2 PRU)
# ============================================================================


def test_anchor_reproduces_both_prus_via_fx_astuce(ledger_db):
    """Anchor INSERT BUY avec fx_at_trade = avg_eur/avg_native => pru_eur ET pru_native exacts.

    C'est l'astuce SPEC §3.1 qui permet aux 21 propres de passer le gate
    byte-identité (Cure #4) malgré une devise étrangère.

    Exemple SK Hynix (si elle était propre — ce qui n'est PAS le cas ici, juste
    pour valider la mécanique de l'astuce) :
      avg_cost_native = 1060 KRW (hypothétique propre)
      avg_cost_eur    = 0.59  EUR (hypothétique propre, à fx 0.000557)
      fx_anchor = avg_eur / avg_native = 0.59 / 1060 = 0.000557

    Sur INSERT BUY qty=1, price_native=1060, fx_at_trade=0.000557 :
      pru_native = 1060 (matche)
      pru_eur    = 1060 x 0.000557 = 0.59 (matche)
    """
    avg_native = 1060.0
    avg_eur = 0.59
    fx_anchor = avg_eur / avg_native

    _insert_trade(
        ledger_db, ticker="ANCHOR_TEST", side="BUY",
        qty=1.0, price_native=avg_native, fees_native=0.0,
        currency="KRW", fx_at_trade=fx_anchor,
        trade_date="2026-05-15", broker_trade_id=None,
        source="anchor_test", is_anchor=1,
    )
    ledger_db.commit()

    row = ledger_db.execute("""
        SELECT SUM(qty * price_native + fees_native) / SUM(qty),
               SUM(qty * price_native * fx_at_trade + fees_native * fx_at_trade) / SUM(qty)
        FROM transactions WHERE ticker='ANCHOR_TEST' AND side='BUY'
    """).fetchone()
    assert row[0] == pytest.approx(avg_native, rel=1e-9)
    assert row[1] == pytest.approx(avg_eur, rel=1e-9)
