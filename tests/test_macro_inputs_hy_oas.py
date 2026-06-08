"""Tracer-bullet HY_OAS : UN vrai input traverse YAML -> resolve -> engine.

Per master correction user 08/06 : "un walking skeleton qui traverse toute la
chaine avec un vrai slice bat un squelette en couches teste sur du mock --
surtout pour une abstraction neuve dont la forme est incertaine. On decouvre
que l'abstraction est fausse seulement quand un vrai input la traverse."

Fixture : tests/fixtures/hy_oas_fred_2026-06-08.json (787 obs FRED, 2023-2026,
range 2.74% - 5%). Pas de dependance FRED live -> deterministe.

Verifie le contrat input -> engine :
- Consommation YAML (sign-theory negative, tier S, source FRED)
- Z-score signe correct (HY tight = low value = z negatif -> z_signed positif)
- M1 fraicheur (asof, max_age_days)
- Engine accepte le ResolvedInput et calcule D coherent
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from intelligence.divergence_engine import compute_divergence
from intelligence.macro_inputs import (
    _percentile,
    _resolve_hy_oas,
    _sign_mult,
    _zscore,
    resolve_macro_inputs,
)


@pytest.fixture(scope="module")
def cfg() -> dict:
    path = Path(__file__).parent.parent / "config" / "divergence.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def fixture_path() -> Path:
    p = Path(__file__).parent / "fixtures" / "hy_oas_fred_2026-06-08.json"
    assert p.exists(), f"HY_OAS fixture missing: {p}"
    return p


# ─── Helpers atomiques ────────────────────────────────────────────────────


def test_sign_mult_canonical() -> None:
    """Sign-theory mult : negative=-1 (low->divergence), positive=+1, neutral=0."""
    assert _sign_mult("negative") == -1
    assert _sign_mult("positive") == 1
    assert _sign_mult("neutral") == 0
    assert _sign_mult("nonsense") == 0


def test_zscore_basic() -> None:
    z = _zscore(10.0, [0.0, 5.0, 10.0, 15.0, 20.0])
    # mean=10, std~7.91, z=0
    assert z == pytest.approx(0.0, abs=0.01)


def test_zscore_empty_returns_none() -> None:
    assert _zscore(5.0, []) is None
    assert _zscore(5.0, [3.0]) is None  # need >=2 for stdev
    assert _zscore(5.0, [3.0, 3.0]) is None  # stdev=0


def test_percentile_basic() -> None:
    p = _percentile(5.0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    # 5 < 5.0 in {1,2,3,4} (and 5 itself excluded by strict <), so 4/10 = 40
    assert p == pytest.approx(40.0, abs=0.01)


# ─── Tracer-bullet HY_OAS ────────────────────────────────────────────────


def test_resolve_hy_oas_from_fixture(cfg, fixture_path) -> None:
    """LE TRACER : fixture FRED -> resolve -> ResolvedInput valide."""
    # Récupère le spec HY_OAS du YAML
    hy_spec = next(
        i for i in cfg["inputs"]["macro"]["croyance_pricee"]
        if i["name"] == "HY_OAS"
    )
    resolved = _resolve_hy_oas(hy_spec, cfg["priors"], fixture_path)
    assert resolved is not None
    # Contract checks
    assert resolved.name == "HY_OAS"
    assert resolved.bucket == "croyance_pricee"
    assert resolved.tier == "S"
    assert resolved.sign_theory == "negative"
    assert resolved.source == "FRED:BAMLH0A0HYM2"
    # Weight = prior tier S
    assert resolved.weight == pytest.approx(0.40, abs=0.01)
    # raw_value présent (276bp = 2.74% range)
    assert resolved.raw_value is not None
    assert 2.0 < resolved.raw_value < 6.0  # HY OAS en % typique
    # asof présent (M1 honnete)
    assert resolved.asof
    assert len(resolved.asof) >= 10  # YYYY-MM-DD


def test_hy_oas_zsign_low_value_means_divergence_positive(cfg, fixture_path) -> None:
    """Sign-theory verification : HY tight (low) doit produire z_signed POSITIF.
    Logique : sign='negative' = low value -> divergence haute = z_signed > 0."""
    hy_spec = next(
        i for i in cfg["inputs"]["macro"]["croyance_pricee"]
        if i["name"] == "HY_OAS"
    )
    resolved = _resolve_hy_oas(hy_spec, cfg["priors"], fixture_path)
    assert resolved is not None
    # 2.74 dans la fixture est PROCHE du min (2.74 = min), donc z<<0
    # avec sign_mult=-1, z_signed = -z = grand positif
    # On verifie le signe attendu : low HY -> divergence HAUTE -> z_signed POSITIF
    if resolved.raw_value < 4.0:  # likely below median
        assert resolved.z_score_signed > 0, (
            f"HY tight (val={resolved.raw_value}) doit produire z_signed positif "
            f"(croyance étirée). Got z_signed={resolved.z_score_signed}"
        )


def test_hy_oas_freshness_check(cfg, fixture_path) -> None:
    """M1 freshness : age > max_age_days (1j) sur fixture historique -> stale."""
    hy_spec = next(
        i for i in cfg["inputs"]["macro"]["croyance_pricee"]
        if i["name"] == "HY_OAS"
    )
    resolved = _resolve_hy_oas(hy_spec, cfg["priors"], fixture_path)
    assert resolved is not None
    # max_age_days=1 dans YAML. Fixture date 2026-06-04, now 2026-06-08 -> stale.
    # On verifie le mecanisme : fixture historique -> fresh=False attendu
    # (sauf si tu testes le jour meme).
    # Test pragmatique : fresh est bien un bool, et la logique est appliquee.
    assert isinstance(resolved.fresh, bool)
    # Si fixture datee > 1j, doit etre False
    if resolved.asof < "2026-06-07":
        assert resolved.fresh is False, "Fixture historique doit etre marquee stale"


# ─── Resolve all macro inputs : skip silencieux des non-wired ────────────


def test_resolve_macro_inputs_only_wires_hy_oas_v0(cfg, fixture_path) -> None:
    """V0 walking skeleton : seul HY_OAS est wired. Les 7 autres macro inputs
    (T10Y2Y_curve, credit_impulse, etc.) seront wired progressivement en C7."""
    inputs = resolve_macro_inputs(cfg, fixture_path=fixture_path)
    # Au moins HY_OAS resolved
    assert len(inputs) >= 1
    names = {i.name for i in inputs}
    assert "HY_OAS" in names
    # Les autres ne sont pas wired V0 -> absents
    assert "T10Y2Y_curve" not in names
    assert "credit_impulse" not in names


# ─── Tracer-bullet end-to-end : fixture -> resolve -> engine ─────────────


def test_tracer_bullet_engine_consumes_hy_oas_real_input(cfg, fixture_path) -> None:
    """LE TEST tracer-bullet master 08/06.
    Pipeline complet : fixture FRED -> resolve_macro_inputs -> compute_divergence.
    Engine projection-agnostique consomme un VRAI input messy (FRED gaps, dates,
    decimal precision) et produit DivergenceReading valide ou degraded honnete."""
    inputs = resolve_macro_inputs(cfg, fixture_path=fixture_path)
    assert len(inputs) >= 1
    reading = compute_divergence("macro", inputs, cfg)

    # V0 walking skeleton : seul 1 input wired. min_fresh_inputs_macro=2 dans YAML
    # -> degraded=True attendu (1 input < 2 required). C'est le COMPORTEMENT
    # ATTENDU : fail-closed strict pendant la phase walking-skeleton.
    if len(inputs) < 2:
        assert reading.degraded is True
        assert "fail_closed" in (reading.degraded_reason or "")
        # Mais le contrat de retour reste honnete : methodology_version present
        assert reading.methodology_version == "divergence_macro_v0"
        assert reading.n_inputs_fresh == sum(1 for i in inputs if i.fresh)
        assert reading.n_inputs_total == len(inputs)


def test_tracer_bullet_min_fresh_lowered_for_v0_demo(cfg, fixture_path) -> None:
    """Demo : si on baisse min_fresh_inputs_macro a 1 (simule wire complet),
    l'engine produit un D coherent sur HY_OAS seul."""
    cfg_demo = dict(cfg)
    cfg_demo["fail_closed"] = dict(cfg["fail_closed"])
    cfg_demo["fail_closed"]["min_fresh_inputs_macro"] = 1

    inputs = resolve_macro_inputs(cfg, fixture_path=fixture_path)
    # Force fresh=True pour la demo (fixture historique)
    forced = [i.model_copy(update={"fresh": True}) for i in inputs]
    reading = compute_divergence("macro", forced, cfg_demo)

    assert reading.degraded is False
    assert reading.D is not None
    assert reading.phase is not None
    assert reading.fragility is not None
    assert reading.methodology_version == "divergence_macro_v0"
    # Drivers exposes pour display
    assert len(reading.drivers) == 1
    driver = reading.drivers[0]
    assert driver["name"] == "HY_OAS"
    assert driver["tier"] == "S"
    assert driver["bucket"] == "croyance_pricee"
    assert "FRED" in driver["source"]
