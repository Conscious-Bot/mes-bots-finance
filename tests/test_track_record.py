"""Tests track_record — rendement PRESAGE-managed flux-neutralisé (audit C).

Logique pure = CI-safe (aucune DB, dates synthétiques explicites).
Intégration DB = @live_data (reproduit les chiffres audit C sur data/bot.db).
"""

import pytest

from intelligence.track_record import (
    INCEPTION,
    _xirr,
    compute_managed_return,
    managed_track_record,
)


def test_zero_flows_perf_equals_nav_change():
    """Sans flux, la perf réelle = variation de NAV pure."""
    r = compute_managed_return(100_000, 110_000, [], "2026-01-01", "2026-04-01")
    assert r["net_contrib_eur"] == 0.0
    assert r["perf_eur"] == 10_000.0
    assert r["perf_pct"] == 10.0


def test_contribution_is_neutralized():
    """Un apport de capital gonfle la NAV mais N'EST PAS de la performance.

    NAV 100k -> 112k, mais on a acheté 10k de capital neuf en cours de route :
    la vraie perf est +2k, pas +12k. C'est le biais #2 que le module corrige.
    """
    flows = [("2026-02-01", -10_000.0)]  # BUY = sortie de cash = apport
    r = compute_managed_return(100_000, 112_000, flows, "2026-01-01", "2026-04-01")
    assert r["net_contrib_eur"] == 10_000.0
    assert r["perf_eur"] == 2_000.0  # (112k-100k) - 10k apport
    assert r["perf_pct"] == 2.0


def test_withdrawal_is_neutralized():
    """Un retrait (SELL net) déprime la NAV sans être une contre-performance."""
    flows = [("2026-02-01", 5_000.0)]  # SELL = entrée de cash = retrait
    r = compute_managed_return(100_000, 98_000, flows, "2026-01-01", "2026-04-01")
    assert r["net_contrib_eur"] == -5_000.0
    # NAV a baissé de 2k mais on a retiré 5k -> vraie perf = +3k
    assert r["perf_eur"] == 3_000.0


def test_xirr_none_without_sign_change():
    """XIRR indéfini si tous les flux ont le même signe (pas de racine)."""
    assert _xirr([("2026-01-01", -100.0), ("2026-02-01", -50.0)]) is None
    assert _xirr([("2026-01-01", 100.0)]) is None


def test_xirr_positive_return():
    """-100 à t0, +110 un an plus tard ≈ +10%/an."""
    x = _xirr([("2026-01-01", -100.0), ("2027-01-01", 110.0)])
    assert x is not None
    assert 0.09 < x < 0.11


def test_low_n_warning_boundary():
    """<90 jours = variance-dominé, flag levé ; >=90j = éteint."""
    short = compute_managed_return(100_000, 101_000, [], "2026-01-01", "2026-02-01")
    assert short["low_n_warning"] is True
    long = compute_managed_return(100_000, 101_000, [], "2026-01-01", "2026-06-01")
    assert long["low_n_warning"] is False


def test_annualization_matches_compounding():
    """+2.88% sur 40j doit annualiser via composition, pas linéairement."""
    r = compute_managed_return(51_243, 52_720, [], "2026-05-23", "2026-07-02")
    assert r["days"] == 40
    # (1+0.0288)^(365/40)-1 ≈ +29-31%, PAS 0.0288*365/40 = +26% linéaire
    assert 28 < r["perf_pct_annualized"] < 32


@pytest.mark.live_data
def test_managed_track_record_reproduces_audit_c():
    """Sur la vraie DB : reproduit le verdict audit C (perf managed honnête).

    Garde-fou contre régression du chiffre proof-of-value. Bornes larges
    (le book bouge chaque jour) mais assez serrées pour attraper une re+
    réintroduction du biais survivorship (qui gonflerait à ~+16%).
    """
    r = managed_track_record()
    assert r is not None
    assert r["inception"] == INCEPTION
    # perf managed flux-neutralisée doit rester MODESTE (proof système, pas latent embarqué).
    # Si un jour ce test voit +15%+, c'est que le biais survivorship est revenu.
    assert -20 < r["perf_pct"] < 12
    assert r["net_contrib_eur"] != 0  # des trades ont eu lieu depuis l'inception
    assert r["xirr_pct"] is not None
