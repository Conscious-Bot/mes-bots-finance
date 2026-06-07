"""Tests C DECISION_QUALITY_ENGINE : base-rate hook + Bayesian shrinkage.

C est scaffold pur tant que daloopa/bigdata connecteur n'est pas wire.
Tests verrouillent :
1. fingerprint extraction pure deterministe
2. base_rate returns None tant que stub raise NotImplementedError (L15)
3. base_rate returns None si dist.n < MIN_N_BASE_RATE
4. shrunk_p comportement : sans base_rate -> observed brut
5. shrunk_p avec base_rate -> pull vers base_rate proportionnel a prior_strength
"""

from __future__ import annotations

from unittest.mock import patch

from track_record.reference_class import (
    MIN_N_BASE_RATE,
    FingerprintInput,
    UniverseDistribution,
    base_rate,
    fingerprint,
    shrunk_p,
)

# === Test 1 : fingerprint pure deterministe ===============================


def test_fingerprint_extraction_canonical():
    fp_in = FingerprintInput(
        ticker="NVDA",
        sector="Semiconductors",
        catalyst_kpi_family="margin",
        setup_bucket="post_beat",
        valuation_percentile=0.85,
    )
    fp = fingerprint(fp_in)
    assert fp["sector"] == "Semiconductors"
    assert fp["catalyst_type"] == "margin"
    assert fp["setup"] == "post_beat"
    # valuation_percentile 0.85 -> quintile int(0.85*5) = 4
    assert fp["valuation_quintile"] == 4


def test_fingerprint_quintile_boundaries():
    # 0.0 -> 0, 0.2 -> 1, 0.4 -> 2, 0.6 -> 3, 0.8 -> 4
    for pct, expected_q in [(0.0, 0), (0.2, 1), (0.4, 2), (0.6, 3), (0.8, 4)]:
        fp = fingerprint(FingerprintInput(
            "X", "S", "k", "b", pct,
        ))
        assert fp["valuation_quintile"] == expected_q


# === Test 2 : base_rate L15 fail-closed sur stub ==========================


def test_base_rate_returns_none_while_stub_raises():
    """Tant que query_universe_excess_returns est stub NotImplementedError,
    base_rate retourne None (L15 fail-closed)."""
    fp = fingerprint(FingerprintInput("NVDA", "Semi", "margin", "post_beat", 0.5))
    result = base_rate(fp, horizon_days=30)
    assert result is None, "base_rate must return None when stub raises"


# === Test 3 : base_rate gating power ======================================


def test_base_rate_returns_none_below_min_n():
    """Meme avec query mocke, si dist.n < MIN_N_BASE_RATE -> None."""
    fp = fingerprint(FingerprintInput("X", "S", "k", "b", 0.5))
    small_dist = UniverseDistribution(
        n=MIN_N_BASE_RATE - 1,  # tout juste sous le seuil
        hit_rate=0.6, mean_excess=0.05,
        median_excess=0.04, p25_excess=-0.02, p75_excess=0.10,
    )
    with patch(
        "track_record.reference_class.query_universe_excess_returns",
        return_value=small_dist,
    ):
        result = base_rate(fp, horizon_days=30)
    assert result is None


def test_base_rate_returns_dict_when_sufficient_n():
    """N >= MIN_N_BASE_RATE -> dict avec p_outperform + n + dist_summary."""
    fp = fingerprint(FingerprintInput("X", "S", "k", "b", 0.5))
    dist = UniverseDistribution(
        n=MIN_N_BASE_RATE + 10,
        hit_rate=0.62, mean_excess=0.045,
        median_excess=0.03, p25_excess=-0.05, p75_excess=0.12,
    )
    with patch(
        "track_record.reference_class.query_universe_excess_returns",
        return_value=dist,
    ):
        result = base_rate(fp, horizon_days=30)
    assert result is not None
    assert result["p_outperform"] == 0.62
    assert result["n"] == MIN_N_BASE_RATE + 10
    assert "median" in result["dist_summary"]


# === Test 4 : shrunk_p sans base_rate -> observed brut ====================


def test_shrunk_p_no_base_rate_returns_observed():
    """Si base_rate is None (L15 : pas dispo) -> observed_p inchange.
    Critique : pas de pull vers chiffre fabrique."""
    p = shrunk_p(observed_p=0.85, observed_n=20, base_rate_p=None)
    assert p == 0.85


def test_shrunk_p_no_base_rate_clamps_to_bounds():
    """Meme sans base_rate, p est clamp dans [0, 1] (defensive)."""
    assert shrunk_p(observed_p=1.5, observed_n=20, base_rate_p=None) == 1.0
    assert shrunk_p(observed_p=-0.2, observed_n=20, base_rate_p=None) == 0.0


# === Test 5 : shrunk_p avec base_rate Bayesian shrinkage ==================


def test_shrunk_p_pulls_toward_base_rate():
    """Petit observed_n + base_rate 0.5 -> p_shrunk tire vers 0.5."""
    # observed 0.9 sur N=5, base rate 0.5, prior strength 15
    # p_shrunk = (0.9*5 + 0.5*15) / (5+15) = (4.5 + 7.5) / 20 = 12/20 = 0.6
    p = shrunk_p(observed_p=0.9, observed_n=5, base_rate_p=0.5, prior_strength=15.0)
    assert abs(p - 0.6) < 1e-9


def test_shrunk_p_strong_n_resists_shrinkage():
    """Grand observed_n -> resistance au pull (observed domine)."""
    # observed 0.9 sur N=100, base rate 0.5, prior strength 15
    # p_shrunk = (0.9*100 + 0.5*15) / (100+15) = (90 + 7.5) / 115 ≈ 0.848
    p = shrunk_p(observed_p=0.9, observed_n=100, base_rate_p=0.5, prior_strength=15.0)
    assert abs(p - 0.848) < 0.01


def test_shrunk_p_returns_base_rate_when_zero_observed():
    """observed_n = 0 et base_rate dispo -> retourne base_rate."""
    p = shrunk_p(observed_p=0.0, observed_n=0, base_rate_p=0.55, prior_strength=15.0)
    # (0*0 + 0.55*15) / (0+15) = 8.25/15 = 0.55
    assert abs(p - 0.55) < 1e-9


# === Test 6 : end-to-end stub doc + propriete clef ========================


def test_query_stub_raises_clear_message():
    """Le stub doit raise NotImplementedError avec doc clair sur le wire."""
    from track_record.reference_class import query_universe_excess_returns
    try:
        query_universe_excess_returns({}, 30)
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError as e:
        msg = str(e)
        assert "daloopa" in msg.lower() or "bigdata" in msg.lower()
