"""Crash-test fail-closed : PRESAGE_SIMULATE_YF_DOWN=1 (rituel mensuel, task #22).

Le flag simule une panne yfinance au chokepoint unique _yf_ticker. Objectif :
prouver que le système dit « je ne sais pas » (None / REFUSÉ / fallback marqué)
au lieu de fabriquer des nombres — L15/L31. CI-safe : flag ON = zéro appel réseau.
"""

from __future__ import annotations

import pytest

from shared import prices


@pytest.fixture(autouse=True)
def _outage(monkeypatch):
    monkeypatch.setenv("PRESAGE_SIMULATE_YF_DOWN", "1")
    prices.reset_caches()
    yield
    prices.reset_caches()


def test_chokepoint_raises():
    with pytest.raises(prices.SimulatedOutage):
        prices._yf_ticker("TSM")


def test_price_paths_fail_closed():
    """Les chemins prix retournent None (contrat module), jamais un nombre."""
    assert prices.get_current_price("TSM") is None
    assert prices.get_current_price_in_eur("TSM") is None


def test_info_path_fails_empty():
    assert prices.get_info("TSM") == {}


def test_fx_falls_back_hardcoded_documented():
    """Panne FX → fallback HARDCODED_FX_TO_EUR (comportement ACTUEL documenté,
    E2 audit 04/07 — deviendra Datum degraded avec le chantier fx gateway #12).
    Le point du crash-test : la valeur vient du fallback, pas d'un live inventé."""
    rate = prices.get_fx_rate("USD", "EUR")
    assert rate == prices.HARDCODED_FX_TO_EUR["USD"]


def test_snapshot_book_refuses_under_outage(monkeypatch):
    """Intégration : sous panne totale, le snapshot book REFUSE (RuntimeError
    visible via _safe_run) — jamais une row fabriquée (L31)."""
    from intelligence import snapshot as snap_mod

    monkeypatch.setattr(
        snap_mod.storage,
        "get_open_positions",
        lambda: [{"ticker": "TSM", "qty": 1, "avg_cost": 100.0}],
    )
    monkeypatch.setattr(snap_mod.storage, "latest_snapshot_hwm", lambda: 1000.0)
    with pytest.raises(RuntimeError, match="REFUSÉ"):
        snap_mod.compute_snapshot()


def test_cluster_value_reports_all_missing(monkeypatch):
    """Intégration : sous panne totale, la grappe remonte TOUS les tickers en
    missing → snapshot_cluster_value refusera (testé côté kill_switch)."""
    from risk import kill_switch as ks

    monkeypatch.setattr(ks, "_cluster_membership", lambda: {"TSM"})
    monkeypatch.setattr(
        ks.storage, "get_open_positions", lambda: [{"ticker": "TSM", "qty": 2}]
    )
    total, missing = ks.compute_cluster_value_eur()
    assert total == 0.0
    assert missing == ["TSM"]
