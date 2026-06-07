"""Tests Phase 1.3 absorption_roadmap — Pydantic ScoringDecision contract.

Verrouille le contrat structure de la sortie scorer :
- Champs requis + bornes
- Literal types catchent typo direction/evidence_strength
- extra='forbid' catche drift LLM (champ invente)
- ticker normalise uppercase + alphanum/.-/
- helper validate_scoring_dict() retourne None sur invalide (L15)
- model_dump() reste compatible dict legacy callers

Si un de ces tests regresse, le contrat scorer a derivé silencieusement.
"""

from __future__ import annotations

import pytest

from intelligence.scoring_types import ScoringDecision, validate_scoring_dict


def _valid_dict():
    """Sample dict valide pour tests positifs."""
    return {
        "version": "v2.0",
        "ticker": "NVDA",
        "horizon_days": 28,
        "base_rate": 0.5,
        "evidence_strength": "moderate",
        "evidence_summary": "Q1 beat + raised guidance",
        "anti_anchoring_reason": "Not 0.5 because evidence specific to Q1",
        "probability": 0.7,
        "direction": "bullish",
        "reasoning": "Beat + raise -> directional bullish 3M",
    }


# --- Positive paths --------------------------------------------------------


def test_valid_dict_instantiates():
    d = _valid_dict()
    decision = ScoringDecision(**d)
    assert decision.probability == 0.7
    assert decision.direction == "bullish"
    assert decision.ticker == "NVDA"


def test_model_dump_compatible_with_legacy_dict():
    """`.model_dump()` retourne un dict avec les memes cles que le legacy.
    Critical : les callers travaillent sur dict, pas sur ScoringDecision."""
    d = _valid_dict()
    out = ScoringDecision(**d).model_dump()
    assert set(out.keys()) == set(d.keys()), (
        f"Keys differ: {set(out.keys()) ^ set(d.keys())}"
    )


def test_validate_scoring_dict_happy_path():
    out = validate_scoring_dict(_valid_dict())
    assert out is not None
    assert out["probability"] == 0.7


# --- Border / clamp paths --------------------------------------------------


@pytest.mark.parametrize("field,bad_value", [
    ("probability", 1.5),
    ("probability", -0.1),
    ("base_rate", 1.5),
    ("base_rate", -0.1),
    ("horizon_days", 0),
    ("horizon_days", 366),
    ("horizon_days", -5),
])
def test_out_of_bounds_returns_none(field, bad_value):
    """Field hors bornes -> None (pas de silent clamp). L15 doctrine."""
    d = _valid_dict()
    d[field] = bad_value
    assert validate_scoring_dict(d) is None, (
        f"{field}={bad_value} doit failer validation (got dict, violation L15)"
    )


@pytest.mark.parametrize("ev", ["UNKNOWN", "Weak ", "extreme", "", None])
def test_evidence_strength_literal_strict(ev):
    """Literal {none, weak, moderate, strong} - typo / casse / vide -> None."""
    d = _valid_dict()
    d["evidence_strength"] = ev
    assert validate_scoring_dict(d) is None


@pytest.mark.parametrize("dr", ["BUY", "long", "Bullish", "", None, "neutral"])
def test_direction_literal_strict(dr):
    """Literal {bullish, bearish, watch} - typo / casse / vide -> None."""
    d = _valid_dict()
    d["direction"] = dr
    assert validate_scoring_dict(d) is None


# --- Ticker normalization --------------------------------------------------


def test_ticker_uppercased():
    d = _valid_dict()
    d["ticker"] = "nvda"
    out = validate_scoring_dict(d)
    assert out is not None
    assert out["ticker"] == "NVDA"


def test_ticker_keeps_dots_and_dashes():
    """Tickers reels : BRK.B, 4063.T (TSE), 005930.KS (KRX)."""
    for t in ("BRK.B", "4063.T", "005930.KS"):
        d = _valid_dict()
        d["ticker"] = t
        out = validate_scoring_dict(d)
        assert out is not None, f"Ticker {t!r} doit etre accepte"
        assert out["ticker"] == t


def test_ticker_rejects_special_chars():
    """Caracteres invalides -> None."""
    for bad in ("NVDA$", "NVDA OPTIONS", "NVDA/CALL", ""):
        d = _valid_dict()
        d["ticker"] = bad
        assert validate_scoring_dict(d) is None


# --- Drift catchers --------------------------------------------------------


def test_extra_field_rejected():
    """`extra='forbid'` : un LLM qui invente un champ doit etre rejete.

    Sans ce gate, drift silencieux : LLM ajoute `confidence_score=0.9`,
    on stocke un dict avec un champ pas dans le ledger SQL = dette."""
    d = _valid_dict()
    d["confidence_level"] = 0.95  # invented field
    assert validate_scoring_dict(d) is None


def test_missing_required_field_rejected():
    """Champs requis manquants -> None."""
    for field in ("version", "ticker", "horizon_days", "base_rate",
                  "evidence_strength", "probability", "direction"):
        d = _valid_dict()
        del d[field]
        assert validate_scoring_dict(d) is None, (
            f"Missing {field} doit failer validation"
        )


# --- String truncation invariants ------------------------------------------


def test_long_strings_rejected():
    """evidence_summary > 500 chars / reasoning > 500 / anti_anchoring > 300
    -> None. Doctrine : le scorer truncate AVANT validate_scoring_dict, donc
    si une string longue arrive ici, c'est un bug upstream qu'on veut catcher."""
    d = _valid_dict()
    d["evidence_summary"] = "x" * 501
    assert validate_scoring_dict(d) is None

    d = _valid_dict()
    d["anti_anchoring_reason"] = "y" * 301
    assert validate_scoring_dict(d) is None

    d = _valid_dict()
    d["reasoning"] = "z" * 501
    assert validate_scoring_dict(d) is None


# --- Frozen invariant ------------------------------------------------------


def test_frozen_decision_immutable():
    """`frozen=True` : impossible de muter apres creation (audit trail).

    Empeche les callers de patcher silencieusement la decision apres
    persistence trace -- divergence trace vs ledger garantie sinon."""
    from pydantic import ValidationError
    decision = ScoringDecision(**_valid_dict())
    with pytest.raises(ValidationError):
        decision.probability = 0.99  # type: ignore[misc]
