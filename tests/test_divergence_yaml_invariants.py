"""Tests verrouillants config/divergence.yaml (cornerstone C5).

Verrouille les invariants doctrinaux du moteur PARTAGÉ avant que le code de
divergence_engine.py soit ecrit (C6). Si un de ces tests fail, le YAML
viole un principe dur de SPEC_CORNERSTONE / CALIBRATION_DOCTRINE.

Tests verrouillants (par regle dure du master) :
- inputs.macro ∩ inputs.micro = ∅ (test critique : pas de double-comptage)
- Chaque input : name, sign, tier, source, max_age_days (M1 triple respecte)
- methodology_versions present pour macro ET micro (self-scoring funnel)
- temporal_splits present + format (L16)
- priors par tier (cible shrinkage CALIBRATION_DOCTRINE §4)
- fail_closed thresholds present (L15)
- rejected explicites (anti-driveby additions futurs)
- output_schema canonique (contrat compute_divergence)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="module")
def cfg() -> dict:
    path = Path(__file__).parent.parent / "config" / "divergence.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def _flat(cfg: dict, scale: str) -> list[dict]:
    """Tous les inputs d'une echelle (concatenation des 3 buckets)."""
    out = []
    for bucket in ("croyance_pricee", "realite_livrable", "phase_reflexive"):
        out.extend(cfg["inputs"][scale].get(bucket, []))
    return out


# ─── TEST CRITIQUE : disjoints macro ∩ micro = ∅ ─────────────────────────


def test_critical_macro_micro_inputs_disjoints(cfg) -> None:
    """LE TEST le plus important. Spec user 07/06 :
    'Inputs disjoints entre les deux echelles (macro = croissance/liquidite ;
    micro = positionnement/crowding ; zero input partage) -> pas de
    double-comptage. L'association est dans la primitive, pas dans un produit
    final.' C'est ce qui le rend brillant plutot que Frankenstein."""
    macro_names = {i["name"] for i in _flat(cfg, "macro")}
    micro_names = {i["name"] for i in _flat(cfg, "micro")}
    overlap = macro_names & micro_names
    assert not overlap, (
        f"Inputs macro ∩ micro non vides : {overlap}. "
        "Double-comptage interdit (SPEC_CORNERSTONE §1)."
    )


# ─── Schema M1 : chaque input porte triple (valeur via source / asof / source)


@pytest.mark.parametrize("scale", ["macro", "micro"])
def test_each_input_has_required_fields(cfg, scale: str) -> None:
    """M1 doctrine + L15 fail-closed : chaque input doit declarer
    name + sign + tier + source + max_age_days. Sans ces 5 champs,
    impossible de calculer le z-score signe + de classifier la freshness."""
    required = ("name", "tier", "sign", "source", "max_age_days")
    for inp in _flat(cfg, scale):
        for fld in required:
            assert fld in inp, (
                f"{scale}/{inp.get('name', '?')} : champ {fld!r} manquant. "
                f"Required: {required}"
            )


@pytest.mark.parametrize("scale", ["macro", "micro"])
def test_each_input_tier_canonical(cfg, scale: str) -> None:
    """Tier dans {S, A, B} (prior de shrinkage CALIBRATION_DOCTRINE §4)."""
    valid = {"S", "A", "B"}
    for inp in _flat(cfg, scale):
        assert inp["tier"] in valid, (
            f"{scale}/{inp['name']} : tier {inp['tier']!r} invalide. "
            f"Doit etre dans {valid}."
        )


@pytest.mark.parametrize("scale", ["macro", "micro"])
def test_each_input_sign_frozen(cfg, scale: str) -> None:
    """Sign theorie figee : positive / negative / neutral. La donnee n'a
    JAMAIS le droit d'inverser le signe (cf HANDOFF_CYCLE_CALIBRATOR §2)."""
    valid = {"positive", "negative", "neutral"}
    for inp in _flat(cfg, scale):
        assert inp["sign"] in valid, (
            f"{scale}/{inp['name']} : sign {inp['sign']!r} invalide. "
            f"Doit etre dans {valid} (theorie figee)."
        )


# ─── Self-scoring : methodology_versions present ─────────────────────────


def test_methodology_versions_per_projection(cfg) -> None:
    """Sans methodology_version, l'engine ne peut pas self-scorer via
    insert_prediction (storage.py:866). Sans self-scoring, c'est un oracle
    non-falsifiable = le defaut qu'on bannit depuis le debut."""
    assert "methodology_versions" in cfg
    mv = cfg["methodology_versions"]
    assert "macro" in mv and mv["macro"], "methodology_versions.macro requis"
    assert "micro" in mv and mv["micro"], "methodology_versions.micro requis"
    assert mv["macro"] != mv["micro"], (
        "macro et micro doivent avoir des methodology_version distincts "
        "(self-scoring separe par projection)"
    )


# ─── Temporal splits (L16 anti-look-ahead) ───────────────────────────────


def test_temporal_splits_present(cfg) -> None:
    """L16 : tout tuning DATÉ avant tuning. Pas de splits => pas de
    backtest legitime."""
    assert "temporal_splits" in cfg
    ts = cfg["temporal_splits"]
    for fld in ("train_window", "val_window", "oos_window"):
        assert fld in ts and ".." in ts[fld], (
            f"temporal_splits.{fld} manquant ou mal format"
        )


# ─── Priors par tier (shrinkage cible) ────────────────────────────────────


def test_priors_per_tier(cfg) -> None:
    """CALIBRATION_DOCTRINE §4 : priors par tier comme cible du shrinkage
    a petit-N. S > A > B."""
    assert "priors" in cfg
    p = cfg["priors"]
    for tier in ("S", "A", "B"):
        assert tier in p, f"priors.{tier} manquant"
        assert 0 < p[tier] < 1, f"priors.{tier} hors [0,1]"
    assert p["S"] > p["A"] > p["B"], (
        f"Priors doivent decroitre S>A>B. Got S={p['S']} A={p['A']} B={p['B']}"
    )


# ─── Fail-closed thresholds (L15) ────────────────────────────────────────


def test_fail_closed_thresholds_present(cfg) -> None:
    """L15 : <min inputs frais -> p_outcome=None. Sans ces seuils, pas de
    fail-closed possible."""
    assert "fail_closed" in cfg
    fc = cfg["fail_closed"]
    for fld in (
        "min_fresh_inputs_macro",
        "min_fresh_inputs_micro",
        "max_age_days_macro",
        "max_age_days_micro",
    ):
        assert fld in fc, f"fail_closed.{fld} manquant"
    # Doctrine PLAN_REFONTE_ALERTES : >20% en alarme = calibration cassee
    assert "alarm_rate_alarm_threshold" in fc
    assert 0 < fc["alarm_rate_alarm_threshold"] <= 0.30


# ─── Rejected explicites (anti-driveby additions) ────────────────────────


@pytest.mark.parametrize("scale,min_rejected", [("macro", 5), ("micro", 3)])
def test_rejected_explicit_with_reason(cfg, scale: str, min_rejected: int) -> None:
    """Chaque input ecarte doit avoir une raison documentee. Sinon un futur
    self/agent peut le re-ajouter sans contrainte = doctrine violee.

    Macro doit rejeter au moins 5 indicateurs (BTC, VIX_level, AAII, Gold,
    DXY, CopperGold, USDJPY_level, TYX_level per diagnostic 08/06).
    Micro doit rejeter au moins 3 (social_sentiment, gamma, SI brut)."""
    rejected = cfg["inputs"][scale].get("rejected", [])
    assert len(rejected) >= min_rejected, (
        f"{scale} : {len(rejected)} rejets, attendu >= {min_rejected}"
    )
    for r in rejected:
        assert r.get("name"), f"{scale}/rejected entry missing name"
        assert r.get("reason"), f"{scale}/{r['name']} missing reason"


# ─── Critical drops du diagnostic 08/06 (audit FP-by-driver) ─────────────


def test_diagnostic_critical_drops_present_in_rejected(cfg) -> None:
    """Le diagnostic audit 08/06 a chiffre que BTC/VIX/USDJPY/Gold/DXY
    representent 64-65% du score CRISE actuel. Ces 5 DOIVENT etre dans
    rejected, sinon la doctrine n'a pas appris du diagnostic."""
    rejected_names = {r["name"] for r in cfg["inputs"]["macro"].get("rejected", [])}
    critical_drops = {
        "BTC_drawdown180", "VIX_level", "USDJPY_level",
        "Gold", "DXY",
    }
    missing = critical_drops - rejected_names
    assert not missing, (
        f"Diagnostic 08/06 (64% bruit) : ces drops critiques manquent "
        f"dans rejected : {missing}. Voir docs/backtest_audits/macro_monitor_audit_2026-06-08.md"
    )


# ─── Output schema canonique (contrat compute_divergence) ────────────────


def test_output_schema_canonical(cfg) -> None:
    """SPEC_CORNERSTONE §7 contrat output figé."""
    assert "output_schema" in cfg
    fields = cfg["output_schema"]["fields"]
    required = ("D", "phase", "fragility", "p_outcome", "band_lo", "band_hi",
                "drivers", "confidence", "effective_asof", "degraded")
    for fld in required:
        assert fld in fields, f"output_schema.fields.{fld} manquant"


# ─── Calibration metadata (METHODE_CALIBRATION_CORNERSTONE) ──────────────


def test_calibration_metadata_canonical(cfg) -> None:
    """Splits purged walk-forward, PR-AUC, baselines (cf §3+§7 du methodo doc)."""
    cal = cfg["calibration"]
    assert cal["labels"]["primary_target"] == "SMH", (
        "Q1 master tranche : SMH primaire. Voir 00_HANDOFF_MASTER.md."
    )
    assert cal["labels"]["secondary_target"] == "SPY"
    assert cal["labels"]["skip_book_target"] is True, (
        "Book trop petit (26j) pour calibration. Q1 master."
    )
    assert -20.0 in cal["labels"]["drawdown_thresholds_pct"], "multi-label -20%"
    assert -10.0 in cal["labels"]["drawdown_thresholds_pct"], "multi-label -10%"
    assert cal["labels"]["forward_horizon_months"] == 3, "H=3M actionnable"
    assert cal["splits"]["method"] == "purged_walk_forward", "PAS k-fold (L16)"
    assert cal["metrics"]["primary"] == "PR-AUC", "robuste imbalance"
    # Baselines à battre
    bls = set(cal["metrics"]["baselines_to_beat"])
    assert "single_best_indicator" in bls, (
        "METHODE §7 : doit battre single-best-indicator OOS sinon fallback"
    )
    assert "equal_weighted" in bls, "CALIBRATION_DOCTRINE §5 humility test"


# ─── Posture : falsification, pas certification ──────────────────────────


def test_posture_falsification(cfg) -> None:
    """METHODE_CALIBRATION_CORNERSTONE §0 : sur les crises N-starved, on
    FALSIFIE le bruit, on ne CERTIFIE pas la prescience. Cette posture
    doit etre explicite dans le YAML."""
    assert cfg["calibration"]["meta"]["posture"] == "falsification_not_certification"
