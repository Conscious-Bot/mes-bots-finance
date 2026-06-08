"""Tests purs de compute_divergence : primitive D/Phi/F sur inputs synthétiques.

L'engine est PROJECTION-AGNOSTIC -- il ne nomme jamais HY_OAS, SMH, BTC. Ces
tests construisent des ResolvedInput synthétiques (signature contractuelle)
pour valider la primitive D/Phi/F + fail-closed + bucket aggregation.

Le tracer-bullet HY_OAS via macro_inputs FRED fixture est dans
test_macro_inputs_hy_oas.py -- complementaire.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from intelligence.divergence_engine import compute_divergence
from intelligence.divergence_schema import DivergenceReading, ResolvedInput


@pytest.fixture(scope="module")
def cfg() -> dict:
    path = Path(__file__).parent.parent / "config" / "divergence.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def _make_input(
    name: str = "X",
    bucket: str = "croyance_pricee",
    tier: str = "S",
    z_signed: float = 1.0,
    weight: float = 0.40,
    fresh: bool = True,
    asof: str = "2026-06-08",
) -> ResolvedInput:
    return ResolvedInput(
        name=name, bucket=bucket, tier=tier,
        sign_theory="negative",
        z_score_signed=z_signed,
        weight=weight,
        asof=asof,
        source="test:fixture",
        fresh=fresh,
        raw_value=None, percentile=None, delta=None,
    )


# ─── Test 1 : fail-closed strict si n_fresh < min ─────────────────────────


def test_fail_closed_below_min_fresh(cfg) -> None:
    """L15 : n_fresh < min_fresh_inputs_macro -> degraded=True, D=None."""
    # min_fresh_inputs_macro = 2 (cf YAML)
    inputs = [_make_input(name="A", fresh=True)]  # only 1 fresh
    r = compute_divergence("macro", inputs, cfg)
    assert r.degraded is True
    assert r.degraded_reason and "fail_closed" in r.degraded_reason
    assert r.D is None
    assert r.phase is None
    assert r.fragility is None
    assert r.n_inputs_fresh == 1
    assert r.n_inputs_total == 1


def test_fail_closed_all_stale(cfg) -> None:
    """3 inputs mais tous stale -> degraded."""
    inputs = [
        _make_input(name=f"X{i}", fresh=False, asof="2024-01-01")
        for i in range(3)
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert r.degraded is True
    assert r.n_inputs_fresh == 0
    assert r.n_inputs_total == 3


# ─── Test 2 : agregation buckets divergence + phase ──────────────────────


def test_divergence_aggregates_pricee_and_livrable(cfg) -> None:
    """D = weighted mean(z_signed) sur croyance_pricee + realite_livrable."""
    inputs = [
        _make_input(name="A", bucket="croyance_pricee", z_signed=2.0, weight=0.40),
        _make_input(name="B", bucket="realite_livrable", z_signed=1.0, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert not r.degraded
    # Weighted mean : (2.0*0.40 + 1.0*0.40) / (0.40+0.40) = 1.5
    assert pytest.approx(1.5, abs=0.01) == r.D


def test_phase_separate_bucket(cfg) -> None:
    """Phi = weighted mean(z_signed) sur phase_reflexive UNIQUEMENT."""
    inputs = [
        _make_input(bucket="croyance_pricee", z_signed=0.0, weight=0.40),
        _make_input(bucket="realite_livrable", z_signed=0.0, weight=0.40),
        _make_input(bucket="phase_reflexive", z_signed=2.0, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert pytest.approx(0.0, abs=0.01) == r.D
    assert r.phase == pytest.approx(2.0, abs=0.01)


def test_phase_neutral_if_no_phase_inputs(cfg) -> None:
    """Pas de phase input -> phi = 0 (neutre, pas degraded)."""
    inputs = [
        _make_input(bucket="croyance_pricee", z_signed=1.0, weight=0.40),
        _make_input(bucket="realite_livrable", z_signed=-1.0, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert pytest.approx(0.0, abs=0.01) == r.D
    assert r.phase == pytest.approx(0.0, abs=0.01)
    assert r.fragility == pytest.approx(0.0, abs=0.01)


# ─── Test 3 : fragilite = |D| * (1 + max(0, phi)) ────────────────────────


def test_fragility_late_reinforcing_amplifies(cfg) -> None:
    """Late (|D|>0) + reinforcing (phi>0) -> F = |D| * (1+phi) > |D|."""
    inputs = [
        _make_input(bucket="croyance_pricee", z_signed=2.0, weight=0.40),
        _make_input(bucket="realite_livrable", z_signed=2.0, weight=0.40),
        _make_input(bucket="phase_reflexive", z_signed=1.0, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    # D = 2.0, phi = 1.0 -> F = 2.0 * (1+1) = 4.0
    assert pytest.approx(2.0, abs=0.01) == r.D
    assert r.phase == pytest.approx(1.0, abs=0.01)
    assert r.fragility == pytest.approx(4.0, abs=0.01)


def test_fragility_late_defaisant_not_amplified(cfg) -> None:
    """Late (|D|>0) + defaisant (phi<0) -> F = |D| (pas amplifie ; clip a 0)."""
    inputs = [
        _make_input(bucket="croyance_pricee", z_signed=2.0, weight=0.40),
        _make_input(bucket="realite_livrable", z_signed=2.0, weight=0.40),
        _make_input(bucket="phase_reflexive", z_signed=-1.0, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert pytest.approx(2.0, abs=0.01) == r.D
    assert r.phase == pytest.approx(-1.0, abs=0.01)
    # phi=-1 -> max(0,-1)=0 -> F = |D|*1 = 2.0
    assert r.fragility == pytest.approx(2.0, abs=0.01)


def test_fragility_uses_absolute_D(cfg) -> None:
    """F = |D| -- meme D negatif amplifie correctement."""
    inputs = [
        _make_input(bucket="croyance_pricee", z_signed=-3.0, weight=0.40),
        _make_input(bucket="realite_livrable", z_signed=-3.0, weight=0.40),
        _make_input(bucket="phase_reflexive", z_signed=0.5, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    # D = -3.0, |D| = 3.0, phi = 0.5 -> F = 3.0 * 1.5 = 4.5
    assert pytest.approx(-3.0, abs=0.01) == r.D
    assert r.fragility == pytest.approx(4.5, abs=0.01)


# ─── Test 4 : methodology_version propagé ─────────────────────────────────


def test_methodology_version_macro_propagated(cfg) -> None:
    inputs = [
        _make_input(bucket="croyance_pricee", weight=0.40),
        _make_input(bucket="realite_livrable", weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert r.methodology_version == "divergence_macro_v0"


def test_methodology_version_micro_propagated(cfg) -> None:
    inputs = [
        _make_input(bucket="croyance_pricee", weight=0.40),
        _make_input(bucket="realite_livrable", weight=0.40),
    ]
    r = compute_divergence("micro", inputs, cfg)
    assert r.methodology_version == "consensus_v0"


# ─── Test 5 : drivers list pour display ───────────────────────────────────


def test_drivers_list_contains_fresh_inputs(cfg) -> None:
    """drivers list expose les inputs fresh pour display (pas pour logique)."""
    inputs = [
        _make_input(name="HIST_FRESH", bucket="croyance_pricee", weight=0.40, fresh=True),
        _make_input(name="HIST_STALE", bucket="realite_livrable", weight=0.40, fresh=False),
        _make_input(name="OTHER", bucket="croyance_pricee", weight=0.40, fresh=True),
    ]
    r = compute_divergence("macro", inputs, cfg)
    names = {d["name"] for d in r.drivers}
    # Stale exclu du compute donc exclu des drivers (drivers = fresh used)
    assert "HIST_FRESH" in names
    assert "OTHER" in names
    assert "HIST_STALE" not in names


# ─── Test 6 : effective_asof = min des fresh ─────────────────────────────


def test_effective_asof_is_oldest_fresh(cfg) -> None:
    """M1 honnete : effective_asof = as-of du fresh le plus VIEUX."""
    inputs = [
        _make_input(bucket="croyance_pricee", asof="2026-06-08", fresh=True, weight=0.40),
        _make_input(bucket="realite_livrable", asof="2026-06-01", fresh=True, weight=0.40),
        _make_input(bucket="phase_reflexive", asof="2026-06-05", fresh=True, weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert r.effective_asof == "2026-06-01"  # le plus vieux


# ─── Test 7 : DivergenceReading frozen ────────────────────────────────────


def test_divergence_reading_frozen(cfg) -> None:
    """Pydantic frozen=True : mutation impossible (anti tampering downstream)."""
    inputs = [
        _make_input(bucket="croyance_pricee", weight=0.40),
        _make_input(bucket="realite_livrable", weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    from pydantic import ValidationError
    with pytest.raises((ValueError, AttributeError, TypeError, ValidationError)):
        r.D = 999.99  # type: ignore[misc]


# ─── Test 8 : p_outcome=None en V0 (calibration C7 a venir) ──────────────


def test_p_outcome_none_v0(cfg) -> None:
    """V0 : pas de probabilite calibree. p_outcome=None tant que C7 pas wire.
    Cela force le caller a presenter 'D=X, F=Y, p_outcome=non calibre encore'
    plutot que fabriquer une probabilite."""
    inputs = [
        _make_input(bucket="croyance_pricee", weight=0.40),
        _make_input(bucket="realite_livrable", weight=0.40),
    ]
    r = compute_divergence("macro", inputs, cfg)
    assert r.p_outcome is None


# ─── Test 9 : ResolvedInput frozen ────────────────────────────────────────


def test_resolved_input_frozen() -> None:
    i = _make_input()
    from pydantic import ValidationError
    with pytest.raises((ValueError, AttributeError, TypeError, ValidationError)):
        i.z_score_signed = 999.99  # type: ignore[misc]
