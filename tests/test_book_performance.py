"""Verrouille le socle de performance — non-régression du défaut du 03/08/2026.

LE DÉFAUT : `portfolio_snapshots.pnl_pct` affichait −1,1 % le 29/07 alors que
le book était à +23,3 %. Il mesurait le LATENT sur lignes TENUES, ignorant
7 221 € de réalisé et le capital réellement injecté. Agrégat partiel présenté
comme un total (L31).

Ces tests échouent si quelqu'un réintroduit l'une des quatre portes du défaut :
  1. un total qui oublie le réalisé,
  2. un pourcentage publié sans réconciliation,
  3. un pourcentage publié sur couverture incomplète,
  4. une seconde lecture du ledger (ADJUST traités différemment).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shared.book_performance import (
    LEDGER_TEST_TICKERS,
    RECONCILIATION_TOL_EUR,
    compute_book_performance,
    format_headline,
)

REAL_DB = Path(__file__).resolve().parent.parent / "data" / "bot.db"


# ── Fabrique de base synthétique ─────────────────────────────────────────────

def _mk(tx: list[tuple], prices: list[tuple], fx: list[tuple]) -> sqlite3.Connection:
    """Base minimale. tx = (id, ticker, side, qty, px, fees, cur, fx, date, source, notes)."""
    cx = sqlite3.connect(":memory:")
    cx.execute("""CREATE TABLE transactions(
        id INTEGER PRIMARY KEY, ticker TEXT, side TEXT, qty REAL, price_native REAL,
        fees_native REAL, currency TEXT, fx_at_trade REAL, trade_date TEXT,
        source TEXT, notes TEXT)""")
    cx.execute("CREATE TABLE price_history(id INTEGER PRIMARY KEY AUTOINCREMENT, "
               "ticker TEXT, asof TEXT, price_native REAL, currency TEXT, source TEXT)")
    cx.execute("CREATE TABLE fx_history(id INTEGER PRIMARY KEY AUTOINCREMENT, "
               "base TEXT, quote TEXT, rate REAL, asof TEXT, source TEXT)")
    cx.executemany("INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?)", tx)
    cx.executemany("INSERT INTO price_history(ticker,asof,price_native,currency,source) "
                   "VALUES(?,?,?,?,'test')", prices)
    cx.executemany("INSERT INTO fx_history(base,quote,rate,asof,source) VALUES(?,?,?,?,'test')", fx)
    return cx


def _simple() -> sqlite3.Connection:
    """1 ligne tenue (AAA, gagne) + 1 ligne soldée (BBB, perd) — réalisé NON nul."""
    return _mk(
        tx=[
            (1, "AAA", "BUY", 10, 100.0, 0.0, "EUR", 1.0, "2026-01-01", "broker", None),
            (2, "BBB", "BUY", 10, 100.0, 0.0, "EUR", 1.0, "2026-01-02", "broker", None),
            (3, "BBB", "SELL", 10, 80.0, 0.0, "EUR", 1.0, "2026-02-01", "broker", None),
        ],
        prices=[("AAA", "2026-03-01", 150.0, "EUR")],
        fx=[("EUR", "EUR", 1.0, "2026-03-01")],
    )


# ── 1. LE test : le total inclut le réalisé ─────────────────────────────────

def test_le_total_inclut_le_realise():
    """Le défaut d'origine : un « P&L » qui n'était que le latent.

    Ici : latent = +500 (AAA), réalisé = −200 (BBB). Un total qui vaudrait
    +500 signifierait que le réalisé a été oublié — exactement le bug.
    """
    p = compute_book_performance(_simple())
    assert p.realized_pnl_eur == pytest.approx(-200.0), "le réalisé doit être compté"
    assert p.unrealized_pnl_eur == pytest.approx(500.0)
    assert p.total_pnl_eur == pytest.approx(300.0), (
        "TOTAL doit être réalisé + latent. S'il vaut le latent seul (+500), "
        "le défaut du 03/08 est réintroduit."
    )
    assert p.total_pnl_eur != pytest.approx(p.unrealized_pnl_eur)


def test_le_rendement_se_calcule_sur_le_capital_injecte():
    """Dénominateur = capital net réellement injecté, pas le coût des lignes tenues.

    Capital = 1000 (AAA) + 1000 (BBB) − 800 (vente BBB) = 1200.
    Un dénominateur « coût des lignes tenues » vaudrait 1000 → +50 %, faux.
    """
    p = compute_book_performance(_simple())
    assert p.capital_net_eur == pytest.approx(1200.0)
    assert p.total_return_pct == pytest.approx(300.0 / 1200.0 * 100.0)


# ── 2. Réconciliation : fail-closed ────────────────────────────────────────

def test_reconciliation_verifiee_sur_base_synthetique():
    p = compute_book_performance(_simple())
    assert p.status == "ok"
    assert abs(p.reconciliation_gap_eur) < RECONCILIATION_TOL_EUR


def test_reconciliation_cassee_ne_publie_aucun_pourcentage():
    """Une vente sur pool vide crée du capital sans réalisé correspondant.

    `ledger_pmp` ignore ce SELL (pas de réalisé fabriqué) mais le capital, lui,
    l'enregistre → l'égalité casse. Le socle DOIT refuser de publier.
    """
    cx = _mk(
        tx=[
            (1, "AAA", "BUY", 10, 100.0, 0.0, "EUR", 1.0, "2026-01-01", "broker", None),
            (2, "ZZZ", "SELL", 5, 50.0, 0.0, "EUR", 1.0, "2026-01-02", "broker", None),
        ],
        prices=[("AAA", "2026-03-01", 100.0, "EUR")],
        fx=[("EUR", "EUR", 1.0, "2026-03-01")],
    )
    p = compute_book_performance(cx)
    assert p.status == "error", "réconciliation cassée → status error"
    assert p.total_return_pct is None, "aucun pourcentage ne doit être publié"
    assert p.error and "réconciliation" in p.error.lower()
    assert "NON RÉCONCILIÉE" in format_headline(p)


# ── 3. L31 : couverture partielle déclarée, jamais silencieuse ──────────────

def test_ligne_sans_prix_rend_le_pourcentage_indisponible():
    cx = _mk(
        tx=[
            (1, "AAA", "BUY", 10, 100.0, 0.0, "EUR", 1.0, "2026-01-01", "broker", None),
            (2, "NOPX", "BUY", 5, 20.0, 0.0, "EUR", 1.0, "2026-01-02", "broker", None),
        ],
        prices=[("AAA", "2026-03-01", 150.0, "EUR")],
        fx=[("EUR", "EUR", 1.0, "2026-03-01")],
    )
    p = compute_book_performance(cx)
    assert p.status == "partial"
    assert p.total_return_pct is None, "L31 : un agrégat partiel n'est pas un total"
    assert "NOPX" in p.missing_price_tickers
    assert any("sans prix" in n for n in p.notes), "la couverture doit être DÉCLARÉE"
    assert "couverture" in format_headline(p)


# ── 4. Provenance et exclusions : déclarées, jamais silencieuses ────────────

def test_lignes_seedees_sont_declarees():
    cx = _mk(
        tx=[(1, "PEA1", "BUY", 3, 100.0, 0.0, "EUR", 1.0, "2026-05-15",
             "migration_anchor_2026-06-09", None)],
        prices=[("PEA1", "2026-06-01", 120.0, "EUR")],
        fx=[("EUR", "EUR", 1.0, "2026-06-01")],
    )
    p = compute_book_performance(cx)
    assert "PEA1" in p.seeded_tickers
    assert "seedé" in p.provenance
    assert any("DATES fictives" in n for n in p.notes), (
        "un PRU reconstitué ne porte pas de date — le socle doit le dire, "
        "sinon une durée de détention fausse sera calculée sur ces lignes"
    )


def test_tickers_de_test_exclus_et_declares():
    smoke = sorted(LEDGER_TEST_TICKERS)[0]
    cx = _mk(
        tx=[
            (1, "AAA", "BUY", 10, 100.0, 0.0, "EUR", 1.0, "2026-01-01", "broker", None),
            (2, smoke, "BUY", 1, 999.0, 0.0, "EUR", 1.0, "2026-01-02", "smoke_test_126", None),
        ],
        prices=[("AAA", "2026-03-01", 100.0, "EUR"), (smoke, "2026-03-01", 9999.0, "EUR")],
        fx=[("EUR", "EUR", 1.0, "2026-03-01")],
    )
    p = compute_book_performance(cx)
    assert smoke in p.excluded_test_tickers
    assert p.capital_net_eur == pytest.approx(1000.0), "le smoke ne doit pas peser"
    assert any("smoke-test" in n for n in p.notes), "l'exclusion doit être déclarée"


# ── 5. Fail-safe : jamais d'exception, toujours un état ─────────────────────

def test_ledger_illisible_rend_un_etat_pas_une_exception():
    cx = sqlite3.connect(":memory:")  # aucune table
    p = compute_book_performance(cx)
    assert p.status == "error"
    assert p.total_return_pct is None
    assert p.error


# ── 6. Une seule lecture du ledger : les ADJUST comptent des deux côtés ─────

def test_adjust_applique_au_capital_ET_au_realise():
    """Le bug des 26 € : le capital ignorait les overrides ADJUST que le
    réalisé appliquait. Deux lectures = deux vérités = réconciliation fausse.
    """
    cx = _mk(
        tx=[
            (1, "AAA", "BUY", 10, 100.0, 0.0, "EUR", 1.0, "2026-01-01", "broker", None),
            (2, "AAA", "ADJUST", 10, 120.0, 0.0, "EUR", 1.0, "2026-01-01", "cure",
             '{"target_tx_id": 1, "reason": "prix broker réel"}'),
        ],
        prices=[("AAA", "2026-03-01", 130.0, "EUR")],
        fx=[("EUR", "EUR", 1.0, "2026-03-01")],
    )
    p = compute_book_performance(cx)
    assert p.capital_net_eur == pytest.approx(1200.0), (
        "l'override ADJUST (120 au lieu de 100) doit s'appliquer au CAPITAL, "
        "pas seulement au PMP — sinon la réconciliation dérive en silence"
    )
    assert p.status == "ok" and abs(p.reconciliation_gap_eur) < RECONCILIATION_TOL_EUR


# ── 7. Intégration : le vrai book se réconcilie ────────────────────────────

@pytest.mark.skipif(not REAL_DB.is_file(), reason="bot.db absent")
def test_le_vrai_book_se_reconcilie():
    cx = sqlite3.connect(f"file:{REAL_DB}?mode=ro&immutable=1", uri=True)
    p = compute_book_performance(cx)
    assert p.status in ("ok", "partial"), f"book non réconcilié : {p.error}"
    assert abs(p.reconciliation_gap_eur) < RECONCILIATION_TOL_EUR
    assert p.realized_pnl_eur != 0.0, "le réalisé du vrai book n'est pas nul"
    assert p.total_pnl_eur != pytest.approx(p.unrealized_pnl_eur, abs=1.0), (
        "sur le vrai book, total et latent DOIVENT différer — c'est le défaut d'origine"
    )
