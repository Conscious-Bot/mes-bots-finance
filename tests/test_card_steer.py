"""Carte-decision #1 etape 3 : tests derive_card_steer + 5 regles fail-closed.

Matrice fail-closed exhaustive (chaque regle declenche REVIEW + bandeau).
Matrice verdict (HOLD / TRIM / EXIT) sur composition exit x size sans fail.
Catch 2 critique : structural intact over-cap -> TRIM (SIZE prime sur HOLD-exit).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from intelligence.card_inputs import CardInputs
from intelligence.card_steer import SteerOutput, SteerVerdict, derive_card_steer


def _make_inputs(**overrides) -> CardInputs:
    """Factory CardInputs neutre (clean = HOLD). Override pour cas test."""
    base = CardInputs(
        thesis_id=1,
        ticker="ASML.AS",
        thesis={"id": 1, "ticker": "ASML.AS", "conviction": 5},
        position_type="priced",
        conviction_current=5,
        conviction_at_entry=5,
        weight_pct=5.0,                # sous cap c5 = 6%
        cap_for_conviction_pct=6.0,
        erosion_verdict="INTACT",
        price_asof_severity="green",   # frais
        thesis_review_age_days=5,      # recent
        structural_justification=None,
        ruin_budget_per_name_pct=1.5,
        allow_add_steer=False,
    )
    return replace(base, **overrides)


# ──── REGLE 1 fail-closed : prix stale rouge ────────────────────────────


def test_rule1_price_stale_rouge_triggers_review() -> None:
    inputs = _make_inputs(price_asof_severity="rouge")
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW
    assert "PRIX STALE" in out.dominant_reason
    assert any("PRIX STALE" in b for b in out.bandeau)


def test_rule1_price_amber_does_not_trigger_review() -> None:
    inputs = _make_inputs(price_asof_severity="amber")
    out = derive_card_steer(inputs)
    assert out.verdict != SteerVerdict.REVIEW


# ──── REGLE 2 fail-closed : these non-revue > 90j ───────────────────────


def test_rule2_thesis_stale_90j_triggers_review() -> None:
    inputs = _make_inputs(thesis_review_age_days=95)
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW
    assert "NON-REVUE 95j" in out.bandeau[0]


def test_rule2_thesis_at_90j_boundary_ok() -> None:
    """Exactement 90j = OK (strict > 90)."""
    inputs = _make_inputs(thesis_review_age_days=90)
    out = derive_card_steer(inputs)
    assert out.verdict != SteerVerdict.REVIEW


# ──── REGLE 3 fail-closed : LLM degraded ─────────────────────────────────


def test_rule3_llm_degraded_triggers_review() -> None:
    inputs = _make_inputs(erosion_verdict="REVIEW_DUE_DEGRADED")
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW
    assert "LLM REFUSE" in out.bandeau[0]


# ──── REGLE 4 fail-closed : cours absent ─────────────────────────────────


def test_rule4_missing_price_triggers_review() -> None:
    """Position ouverte mais last_price_native None -> REVIEW."""
    class _FakeBookLine:
        qty = 4.0
        last_price_native = None
    inputs = _make_inputs(book_line=_FakeBookLine())
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW
    assert any("COURS ABSENT" in b for b in out.bandeau)


def test_rule4_zero_qty_no_review() -> None:
    """qty=0 (these orpheline) ne declenche pas la regle 4."""
    class _FakeBookLine:
        qty = 0
        last_price_native = None
    inputs = _make_inputs(book_line=_FakeBookLine())
    out = derive_card_steer(inputs)
    assert out.verdict != SteerVerdict.REVIEW or "COURS ABSENT" not in (out.dominant_reason or "")


# ──── REGLE 5 fail-closed : structural sans justification (Catch 1) ──────


def test_rule5_structural_without_justification_triggers_review() -> None:
    """LE TEST CATCH 1 amplifie : structural sans justif -> REVIEW."""
    inputs = _make_inputs(position_type="structural", structural_justification=None)
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW
    assert "STRUCTURAL SANS JUSTIFICATION" in out.bandeau[0]


def test_rule5_structural_with_justification_ok() -> None:
    inputs = _make_inputs(
        position_type="structural",
        structural_justification="Monopole EUV verified",
    )
    out = derive_card_steer(inputs)
    assert out.verdict != SteerVerdict.REVIEW


def test_rule5_priced_without_justification_ok() -> None:
    """Priced n'a pas besoin de justification."""
    inputs = _make_inputs(position_type="priced", structural_justification=None)
    out = derive_card_steer(inputs)
    assert out.verdict != SteerVerdict.REVIEW


# ──── Multi-regles : bandeau accumule ────────────────────────────────────


def test_multiple_fail_closed_accumulates_bandeau() -> None:
    inputs = _make_inputs(
        price_asof_severity="rouge",
        thesis_review_age_days=100,
        erosion_verdict="REVIEW_DUE_DEGRADED",
    )
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW
    assert len(out.bandeau) == 3


# ──── EXIT prioritaire sur tout ──────────────────────────────────────────


def test_invalidation_hit_returns_exit() -> None:
    inputs = _make_inputs(erosion_verdict="INVALIDATION_HIT")
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.EXIT
    assert out.exit_action == "exit_now"


# ──── CRITIQUE Catch 2 : structural intact over-cap -> TRIM ──────────────


def test_critical_catch2_structural_intact_over_cap_returns_trim() -> None:
    """LE TEST CATCH 2 (red-team user 07/06) :
    structural + INTACT + 8.31% > cap 6% (ASML reel) doit retourner TRIM_TO_X
    parce que SIZE prime sur HOLD-exit. Le type structural NE doit PAS exempter
    le sizing du cap c5."""
    inputs = _make_inputs(
        position_type="structural",
        structural_justification="Monopole EUV verified",
        erosion_verdict="INTACT",
        weight_pct=8.31,
        conviction_current=5,
        cap_for_conviction_pct=6.0,
    )
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.TRIM_TO_X
    assert out.exit_action == "hold"
    assert out.size_action in ("rightsize", "urgent_rightsize")
    assert out.target_qty_delta_pct < 0
    assert "over-cap" in out.dominant_reason


# ──── HOLD propre : intact + sous cap ────────────────────────────────────


def test_intact_under_cap_returns_hold() -> None:
    inputs = _make_inputs(
        position_type="priced",
        erosion_verdict="INTACT",
        weight_pct=4.0,
        conviction_current=5,
        cap_for_conviction_pct=6.0,
    )
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.HOLD
    assert out.exit_action == "hold"
    assert out.size_action == "no_action"


# ──── ADD desactive par defaut (anti-FOMO) ───────────────────────────────


def test_add_disabled_by_default_returns_hold() -> None:
    """Meme avec under-cap-room + INTACT, allow_add_steer=False -> HOLD."""
    inputs = _make_inputs(
        position_type="priced",
        erosion_verdict="INTACT",
        weight_pct=2.0,                # bien sous cap
        cap_for_conviction_pct=6.0,
        allow_add_steer=False,
    )
    out = derive_card_steer(inputs)
    # Doit etre HOLD (pas ADD) tant que allow_add_steer=False
    assert out.verdict == SteerVerdict.HOLD


# ──── priced + EROSION_DETECTED -> TRIM (tighten_stop) ───────────────────


def test_priced_erosion_returns_trim() -> None:
    inputs = _make_inputs(
        position_type="priced",
        erosion_verdict="EROSION_DETECTED",
        weight_pct=4.0,
        cap_for_conviction_pct=6.0,
    )
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.TRIM_TO_X
    assert out.exit_action == "tighten_stop"


# ──── STALE_UNUPDATED -> REVIEW (exit_policy review) ────────────────────


def test_stale_unupdated_returns_review() -> None:
    inputs = _make_inputs(erosion_verdict="STALE_UNUPDATED")
    out = derive_card_steer(inputs)
    assert out.verdict == SteerVerdict.REVIEW


# ──── SteerOutput frozen ─────────────────────────────────────────────────


def test_steer_output_frozen() -> None:
    inputs = _make_inputs()
    out = derive_card_steer(inputs)
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        out.verdict = SteerVerdict.EXIT  # type: ignore[misc]


# ──── Smoke isinstance SteerOutput ───────────────────────────────────────


def test_returns_steer_output_type() -> None:
    inputs = _make_inputs()
    out = derive_card_steer(inputs)
    assert isinstance(out, SteerOutput)
