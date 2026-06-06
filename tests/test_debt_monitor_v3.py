"""V3 invariants debt_monitor : BTC_drawdown180 + FedBalance_yoy + MfgIP_yoy recalibre.

Task #42 (portage prod 01/06). Validation OOS dans
docs/backtests/debt_composite_2017_2026_v3_insample.csv (7/8 dates non-anchor
+ 5/5 regimes soutenus, cf scripts/backtest_macro_composite.py).

Tests verifient :
 - INDICATOR_CONFIG V3 (BTC supprime, BTC_drawdown180 present + idem
   FedBalance)
 - classify_phase sur nouveaux phase_ranges V3
 - smoke fetch des 2 nouveaux indicators (skip si offline)
"""

from __future__ import annotations

import os

import pytest

from intelligence.debt_monitor import (
    INDICATOR_CONFIG,
    classify_phase,
)


class TestConfigV3:
    """Sanity sur INDICATOR_CONFIG apres swap V3."""

    def test_btc_level_retire(self):
        """BTC niveau brut retire en V3 (remplace par drawdown180)."""
        assert "BTC" not in INDICATOR_CONFIG

    def test_btc_drawdown180_present(self):
        cfg = INDICATOR_CONFIG.get("BTC_drawdown180")
        assert cfg is not None
        assert cfg["tier"] == 1
        assert cfg["weight"] == 1.0
        assert cfg["source"] == "derived:btc_drawdown180"

    def test_fedbalance_level_retire(self):
        """FedBalance niveau brut retire en V3 (remplace par YoY)."""
        assert "FedBalance" not in INDICATOR_CONFIG

    def test_fedbalance_yoy_present(self):
        cfg = INDICATOR_CONFIG.get("FedBalance_yoy")
        assert cfg is not None
        assert cfg["tier"] == 3
        assert cfg["weight"] == 0.5
        assert cfg["source"] == "fred:WALCL_yoy"

    def test_mfgip_yoy_v3_phase_ranges(self):
        """MfgIP_yoy V3 hard-reality 06/06 : bands (0.95, 0.28) alignes,
        plus stricte que V2. -5% P4 verrou anti-regression preserve.
        """
        cfg = INDICATOR_CONFIG["MfgIP_yoy"]
        ranges = cfg["phase_ranges"]
        assert ranges[0] == (-999, -5, 4)
        assert ranges[1] == (-5, 0, 3)  # was (-5, -2, 3), v3 plus stricte


class TestClassifyV3:
    """Invariants classification sur nouveaux phase_ranges."""

    def test_btc_drawdown180_capitulation(self):
        """BTC drawdown <-50% = P4 (COVID -55%, 2022 -75%)."""
        ranges = INDICATOR_CONFIG["BTC_drawdown180"]["phase_ranges"]
        assert classify_phase(-55.0, ranges) == 4
        assert classify_phase(-75.0, ranges) == 4

    def test_btc_drawdown180_bear_modere(self):
        """BTC drawdown -30 a -50% = P3 (SVB tail era)."""
        ranges = INDICATOR_CONFIG["BTC_drawdown180"]["phase_ranges"]
        assert classify_phase(-40.0, ranges) == 3
        assert classify_phase(-35.0, ranges) == 3

    def test_btc_drawdown180_correction(self):
        """BTC drawdown -15 a -30% = P2 (correction normale)."""
        ranges = INDICATOR_CONFIG["BTC_drawdown180"]["phase_ranges"]
        assert classify_phase(-20.0, ranges) == 2

    def test_btc_drawdown180_near_ath(self):
        """BTC drawdown > -15% = P1 (risk-on near ATH)."""
        ranges = INDICATOR_CONFIG["BTC_drawdown180"]["phase_ranges"]
        assert classify_phase(-5.0, ranges) == 1
        assert classify_phase(0.0, ranges) == 1

    def test_fedbalance_yoy_qe_emergency(self):
        """FedBalance YoY > +20% = P4 (COVID emergency +30%)."""
        ranges = INDICATOR_CONFIG["FedBalance_yoy"]["phase_ranges"]
        assert classify_phase(30.0, ranges) == 4

    def test_fedbalance_yoy_qe_intervention(self):
        """FedBalance YoY +5 a +20% = P3 (QE actif)."""
        ranges = INDICATOR_CONFIG["FedBalance_yoy"]["phase_ranges"]
        assert classify_phase(10.0, ranges) == 3

    def test_fedbalance_yoy_stable(self):
        """FedBalance YoY +- 5% = P1 (stable normal)."""
        ranges = INDICATOR_CONFIG["FedBalance_yoy"]["phase_ranges"]
        assert classify_phase(0.0, ranges) == 1
        assert classify_phase(3.0, ranges) == 1

    def test_fedbalance_yoy_qt_modere(self):
        """FedBalance YoY -10 a -5% = P2 (QT modere)."""
        ranges = INDICATOR_CONFIG["FedBalance_yoy"]["phase_ranges"]
        assert classify_phase(-7.0, ranges) == 2

    def test_fedbalance_yoy_qt_agressif(self):
        """FedBalance YoY < -10% = P3 (QT agressif)."""
        ranges = INDICATOR_CONFIG["FedBalance_yoy"]["phase_ranges"]
        assert classify_phase(-15.0, ranges) == 3

    def test_mfgip_yoy_recession_profonde(self):
        """V3 : MfgIP -7% = P4 (recession profonde 2008/COVID)."""
        ranges = INDICATOR_CONFIG["MfgIP_yoy"]["phase_ranges"]
        assert classify_phase(-7.0, ranges) == 4

    def test_mfgip_yoy_recession_moderee_v3(self):
        """V3 : MfgIP -3% = P3 (recession moderee, n'etait pas P4 en V1).

        Verrou anti-regression : si quelqu'un revient sur le seuil P4 -2%,
        ce test casse explicitement.
        """
        ranges = INDICATOR_CONFIG["MfgIP_yoy"]["phase_ranges"]
        assert classify_phase(-3.0, ranges) == 3

    def test_mfgip_yoy_sluggish(self):
        """MfgIP -1% = P3 (v3 hard-reality : <0 = contraction = P3, plus
        seulement sluggish)."""
        ranges = INDICATOR_CONFIG["MfgIP_yoy"]["phase_ranges"]
        assert classify_phase(-1.0, ranges) == 3

    def test_mfgip_yoy_expansion(self):
        """MfgIP > 0.95% = P1 (vraie expansion saine).
        0.5% = P2 (ralenti, v3 plus stricte que V1 ou >=0 = P1)."""
        ranges = INDICATOR_CONFIG["MfgIP_yoy"]["phase_ranges"]
        assert classify_phase(0.5, ranges) == 2  # ralenti
        assert classify_phase(3.0, ranges) == 1  # expansion saine


class TestSmokeV3Fetch:
    """Smoke tests fetch live : skip si offline ou pas de FRED_API_KEY."""

    @pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Pas de fetch externe en CI",
    )
    def test_btc_drawdown180_fetch_smoke(self):
        """Fetch reel : retourne float dans [-100, 100] ou None si offline."""
        from intelligence.debt_monitor import _fetch_btc_drawdown180

        result = _fetch_btc_drawdown180()
        if result is None:
            pytest.skip("yfinance offline / rate-limited")
        assert -100.0 <= result <= 100.0
        # Drawdown ne peut pas etre strictement > 0 (max(180j) >= current)
        # mais tolerance epsilon float pour le cas current == max
        assert result <= 1e-6, f"drawdown180 should be <= 0, got {result}"

    @pytest.mark.skipif(
        not os.environ.get("FRED_API_KEY"),
        reason="FRED_API_KEY absente",
    )
    @pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Pas de fetch externe en CI",
    )
    def test_fedbalance_yoy_fetch_smoke(self):
        """Fetch reel FRED WALCL YoY."""
        from intelligence.debt_monitor import _fetch_fred_walcl_yoy

        result = _fetch_fred_walcl_yoy()
        if result is None:
            pytest.skip("FRED offline / rate-limited")
        # Fed balance YoY raisonnablement dans +- 50%
        assert -50.0 <= result <= 50.0
