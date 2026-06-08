"""Tests verrouillants : P&L position canonique EUR (#118 fix FX).

Walking-skeleton sur 4 cas reels :
  - SK Hynix (KRW, avg_cost legacy EUR) -- cas qui revele le bug FX
  - AMD (USD, avg_cost native USD post-backfill EUR) -- cas crucial cite Olivier
  - ASML.AS (EUR native) -- cas controle, avg_cost == avg_cost_eur
  - Mitsubishi 7011.T (JPY, avg_cost legacy EUR)

Conventions verrouillees apres migration 0043 :
  - avg_cost_eur : canonique EUR pour tous les tickers
  - pnl_position_pct_eur(position) = (value_eur_now / cost_basis_eur - 1) * 100
"""

from __future__ import annotations

import pytest

from shared.position_pnl import pnl_position_eur, pnl_position_pct_eur


def _pos(**fields):
    """Position dict factory."""
    return fields


# === Test 1 : fail-closed sur inputs manquants =============================


def test_returns_none_if_qty_missing() -> None:
    assert pnl_position_pct_eur(_pos(avg_cost_eur=100.0, ticker="X")) is None
    assert pnl_position_pct_eur(_pos(qty=0, avg_cost_eur=100.0, ticker="X")) is None


def test_returns_none_if_avg_cost_eur_missing() -> None:
    assert pnl_position_pct_eur(_pos(qty=10, ticker="X")) is None
    assert pnl_position_pct_eur(_pos(qty=10, avg_cost_eur=None, ticker="X")) is None


def test_returns_none_if_ticker_missing() -> None:
    assert pnl_position_pct_eur(_pos(qty=10, avg_cost_eur=100.0)) is None


# === Test 2 : Walking-skeleton AMD (USD, post-backfill avg_cost_eur=127.20) =


def test_walking_skeleton_amd_usd_canonical() -> None:
    """AMD : avg_cost 146.63 USD -> avg_cost_eur 127.20 EUR (backfill 0043).
    Current 466.38 USD -> value_eur via FX ~404.58 EUR/share, qty 4.12.

    cost_basis_eur = 4.12 * 127.20 = 524.06 EUR
    value_eur_now = 4.12 * 466.38 * 0.8675 = 1666.84 EUR
    pnl_position_pct = (1666.84 / 524.06 - 1) * 100 = +218.0% (le vrai P&L Olivier)
    """
    pos = _pos(
        qty=4.12, avg_cost_eur=127.20, ticker="AMD",
        last_price_native=466.38, fx_rate_to_eur=0.8675,
    )
    pct = pnl_position_pct_eur(pos)
    assert pct is not None
    assert pct == pytest.approx(218.0, abs=1.0)


# === Test 3 : Walking-skeleton SK Hynix (KRW, avg_cost legacy EUR) =========


def test_walking_skeleton_sk_hynix_krw_canonical() -> None:
    """SK Hynix : avg_cost 1060 KRW-legacy-EUR (pas converti, deja EUR).
    Current 2_070_000 KRW * 0.000556 = 1151 EUR/share. qty 1.51.

    cost_basis_eur = 1.51 * 1060 = 1600.6 EUR
    value_eur_now = 1.51 * 2_070_000 * 0.000556 = 1738.0 EUR
    pnl_position_pct = (1738.0 / 1600.6 - 1) * 100 = +8.58%
    """
    pos = _pos(
        qty=1.51, avg_cost_eur=1060.0, ticker="000660.KS",
        last_price_native=2_070_000.0, fx_rate_to_eur=0.000556,
    )
    pct = pnl_position_pct_eur(pos)
    assert pct is not None
    assert pct == pytest.approx(8.58, abs=0.2)


# === Test 4 : Walking-skeleton ASML.AS (EUR native, avg_cost EUR) ==========


def test_walking_skeleton_asml_eur_native_canonical() -> None:
    """ASML.AS : avg_cost 820.95 EUR. Current 1462.20 EUR.

    Pas de conversion : tout en EUR cohérent.
    pnl_pct = (1462.20 / 820.95 - 1) * 100 = +78.1%
    """
    pos = _pos(
        qty=3.0, avg_cost_eur=820.95, ticker="ASML.AS",
        last_price_native=1462.20, fx_rate_to_eur=1.0,
    )
    pct = pnl_position_pct_eur(pos)
    assert pct is not None
    assert pct == pytest.approx(78.1, abs=0.5)


# === Test 5 : Mitsubishi 7011.T (JPY, avg_cost legacy EUR) =================


def test_walking_skeleton_mitsubishi_jpy_canonical() -> None:
    """7011.T : avg_cost 22.18 EUR-legacy. Current 3790 JPY * 0.005414 = 20.52 EUR.

    cost_basis_eur = 112.73 * 22.18 = 2500.35 EUR
    value_eur_now = 112.73 * 3790 * 0.005414 = 2312.83 EUR
    pnl_pct = (2312.83 / 2500.35 - 1) * 100 = -7.5% (descente coherente)
    """
    pos = _pos(
        qty=112.73, avg_cost_eur=22.18, ticker="7011.T",
        last_price_native=3790.0, fx_rate_to_eur=0.005414,
    )
    pct = pnl_position_pct_eur(pos)
    assert pct is not None
    assert pct == pytest.approx(-7.5, abs=0.5)


# === Test 6 : Cohérence entre pct et eur ===================================


def test_pnl_eur_consistent_with_pct() -> None:
    """pnl_position_eur(p) doit etre coherent avec pct * cost_basis."""
    pos = _pos(
        qty=10.0, avg_cost_eur=100.0, ticker="TEST",
        last_price_native=120.0, fx_rate_to_eur=1.0,
    )
    pct = pnl_position_pct_eur(pos)
    eur = pnl_position_eur(pos)
    assert pct == pytest.approx(20.0, abs=0.01)
    # cost_basis = 10 * 100 = 1000, gain = 20%, donc eur = +200
    assert eur == pytest.approx(200.0, abs=0.1)
