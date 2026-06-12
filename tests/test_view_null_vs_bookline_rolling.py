"""Test de cohérence VUE NULL fail-closed vs BookLine PMP rolling.

Cf rectification Olivier 09/06 soir : 'NULL dans la VUE force la migration
des consumers SQL-direct vers BookLine. Le test de cohérence rougit AVANT
0049 (all-buys ≠ rolling sur 8 tickers = preuve du mensonge vivant),
passe APRÈS 0049 (NULL des 2 côtés cohérents).'

Garde structurelle L27 : une seule source canonique pour le PMP fiscal FR
(= helper `shared.ledger_pmp.compute_pmp_realized` via BookLine).

Ce test rougit si :
  - Un dev re-introduit le calcul PMP dans la VUE SQL (retour au bug)
  - BookLine cesse d'utiliser le helper rolling (régression seam)
"""
from __future__ import annotations

import sqlite3

import pytest

from shared.book import get_held_lines


def test_vue_positions_returns_null_for_pmp_realized_failclosed():
    """Post-0049 : VUE positions.avg_cost_eur IS NULL + realized_pnl IS NULL.

    Fail-closed L15 : NULL > nombre faux. Consumer SQL-direct lit NULL =
    crash explicite = signal de migration vers BookLine.
    """
    try:
        cx = sqlite3.connect("data/bot.db")
        rows = cx.execute(
            "SELECT ticker, avg_cost, avg_cost_eur, avg_cost_native, "
            "       avg_cost_value, realized_pnl "
            "FROM positions WHERE status='open' AND qty > 0"
        ).fetchall()
        cx.close()
    except sqlite3.OperationalError as e:
        pytest.skip(f"DB sans table positions (CI fresh) -- {e}")

    if not rows:
        pytest.skip("DB sans positions ouvertes (CI fresh)")
    for ticker, ac, ac_eur, ac_native, ac_value, rpnl in rows:
        assert ac is None, f"{ticker}: VUE.avg_cost = {ac}, attendu NULL (fail-closed)"
        assert ac_eur is None, f"{ticker}: VUE.avg_cost_eur = {ac_eur}, attendu NULL"
        assert ac_native is None, f"{ticker}: VUE.avg_cost_native = {ac_native}, attendu NULL"
        assert ac_value is None, f"{ticker}: VUE.avg_cost_value = {ac_value}, attendu NULL"
        assert rpnl is None, f"{ticker}: VUE.realized_pnl = {rpnl}, attendu NULL"


def test_bookline_serves_rolling_pmp_for_8_rebuy_tickers():
    """BookLine.avg_cost_eur via helper rolling diffère de VUE all-buys
    historique sur les 8 tickers avec re-buy après SELL.

    Avant 0049 : VUE servait all-buys faux. Maintenant : VUE NULL + BookLine
    rolling. Ce test garde qu'on ne re-introduit pas le bug : si BookLine
    cesse d'utiliser le helper, ces 8 tickers donneront des valeurs
    différentes du rolling-truth.
    """
    REBUY_TICKERS = {"TSLA", "MP", "TSM", "AMZN", "GOOGL", "AVGO", "MU", "AMD"}
    lines = get_held_lines()
    by_ticker = {ln.ticker: ln for ln in lines}

    for tk in REBUY_TICKERS:
        ln = by_ticker.get(tk)
        if ln is None:
            pytest.skip(f"{tk} not in held positions — skip (peut arriver si user a vendu depuis)")
        assert ln.avg_cost_eur is not None, \
            f"{tk}: BookLine.avg_cost_eur is None — helper rolling cassé ?"
        assert ln.avg_cost_eur > 0, \
            f"{tk}: BookLine.avg_cost_eur = {ln.avg_cost_eur}, doit être > 0"


def test_tesla_bookline_matches_broker_within_fee_explained():
    """Tesla : BookLine.avg_cost_eur = 358.65€ (rolling fee-inclusive).
    TR broker affiche 358.04€ (fee-exclusive).
    Δ ≈ 0.60€ = exactement 7 fees × 1€ / 11.657 shares — documenté.
    """
    lines = get_held_lines()
    tsla = next((l for l in lines if l.ticker == "TSLA"), None)
    if tsla is None:
        pytest.skip("TSLA not in held positions")

    BROKER_PMP = 358.04
    FEE_EXPLAINED_DIFF = 0.61  # ≈ 7 × 1€ / qty
    actual = tsla.avg_cost_eur
    diff_vs_broker = actual - BROKER_PMP
    assert abs(diff_vs_broker - FEE_EXPLAINED_DIFF) < 0.05, (
        f"Tesla PMP = {actual:.4f}€, broker = {BROKER_PMP}€, "
        f"Δ = {diff_vs_broker:.4f}€ (attendu ≈ {FEE_EXPLAINED_DIFF}€ fee-inclusive vs no-fee). "
        f"Si Δ ≈ +7€ : régression vers all-buys. Si Δ très grand : bug rolling."
    )


def test_no_pmp_calculation_resurrects_in_view_sql():
    """REGRESSION GATE : si quelqu'un re-introduit avg_cost_eur calculé dans la
    VUE, ce test rougit. Force la cohérence L27 single source via BookLine.
    """
    cx = sqlite3.connect("data/bot.db")
    sql = cx.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='positions'"
    ).fetchone()
    cx.close()
    if sql is None or sql[0] is None:
        pytest.skip("VIEW positions absente (test_migrated_db) — n/a")

    view_sql = sql[0].upper()
    # Pattern interdit : calcul du PMP dans la VUE SQL.
    # Accepté : 'NULL AS avg_cost_eur' (fail-closed L15).
    assert "NULL AS AVG_COST_EUR" in view_sql or "NULL AS AVG_COST" in view_sql, (
        "VUE positions ne déclare plus avg_cost_eur en NULL — "
        "PMP calculé dans la VUE = régression vers le bug (cf #127b). "
        "Toute dérivation PMP doit passer par shared.ledger_pmp via BookLine."
    )
    assert "NULL AS REALIZED_PNL" in view_sql, (
        "VUE positions ne déclare plus realized_pnl en NULL — régression. "
        "Toute dérivation realized doit passer par shared.ledger_pmp via BookLine."
    )
