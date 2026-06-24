"""Tests position_steer : matrice type x verdict + sizing independant.

Spec user red-team 07/06 Catch 2 :
"position_type et cap sont 2 axes orthogonaux. Un structural intact 2x-over-cap
-> exit:hold + size:rightsize. Ne laisse pas le type exempter la taille."

Tests :
- Matrice exhaustive ExitPolicy : 3 types x (5 verdicts + None) = 18 cas
- Sizing independance : meme weight -> meme SizeAction quel que soit type/verdict
- CRITIQUE Catch 2 : structural + intact + over-cap -> exit:hold + size:rightsize
- Sizing thresholds : sous cap -> no_action, over cap -> rightsize, > 1.5x -> urgent
- Verdict None graceful -> traite comme INTACT
- Type invalide -> raises
"""

from __future__ import annotations

import pytest

from intelligence.position_steer import (
    Steer,
    derive_steer,
)

# ─── Test 1 : Matrice exit_policy.action exhaustive ──────────────────────


@pytest.mark.parametrize("position_type, verdict, expected_action", [
    # structural
    ("structural", "INTACT",               "hold"),
    ("structural", "EROSION_DETECTED",     "review"),
    ("structural", "INVALIDATION_HIT",     "exit_now"),
    ("structural", "STALE_UNUPDATED",      "review"),
    ("structural", "REVIEW_DUE_DEGRADED",  "review_due_degraded"),
    ("structural", None,                   "hold"),
    # priced
    ("priced", "INTACT",                   "hold"),
    ("priced", "EROSION_DETECTED",         "tighten_stop"),
    ("priced", "INVALIDATION_HIT",         "exit_now"),
    ("priced", "STALE_UNUPDATED",          "review"),
    ("priced", "REVIEW_DUE_DEGRADED",      "review_due_degraded"),
    ("priced", None,                       "hold"),
    # tactical
    ("tactical", "INTACT",                 "hold"),
    ("tactical", "EROSION_DETECTED",       "trim_aggressive"),
    ("tactical", "INVALIDATION_HIT",       "exit_now"),
    ("tactical", "STALE_UNUPDATED",        "review"),
    ("tactical", "REVIEW_DUE_DEGRADED",    "review_due_degraded"),
    ("tactical", None,                     "hold"),
])
def test_exit_policy_matrix(position_type: str, verdict: str | None, expected_action: str) -> None:
    s = derive_steer(position_type, verdict, current_weight_pct=3.0, conviction=5)
    assert s.exit_policy.action == expected_action, (
        f"Cas ({position_type}, {verdict}) : attendu {expected_action}, "
        f"obtenu {s.exit_policy.action}"
    )


# ─── Test 2 : structural impose forbidden full-exit-on-price ─────────────


def test_structural_forbidden_includes_price_exit() -> None:
    """Catch user red-team : structural NEVER exits on price drop."""
    s = derive_steer("structural", "INTACT", 3.0, 5)
    assert "full_exit_on_price_drop" in s.exit_policy.forbidden
    assert "trim_on_volatility" in s.exit_policy.forbidden


def test_priced_does_not_forbid_price_exit() -> None:
    """Priced exits sur stop-prix normal -- pas dans forbidden."""
    s = derive_steer("priced", "INTACT", 3.0, 5)
    assert "full_exit_on_price_drop" not in s.exit_policy.forbidden
    # mais ignore_existing_stop est forbidden
    assert "ignore_existing_stop" in s.exit_policy.forbidden


def test_tactical_forbidden_hold_through_catalyst() -> None:
    """Tactical doit jamais hold-through-catalyst-miss."""
    s = derive_steer("tactical", "INTACT", 3.0, 5)
    assert "hold_through_catalyst_miss" in s.exit_policy.forbidden


# ─── Test 3 : CRITIQUE Catch 2 — type N'EXEMPTE PAS la taille ────────────


def test_critical_catch2_structural_intact_over_cap_still_rightsizes() -> None:
    """LE TEST CATCH 2 : ASML cas reel post-refonte 24/06 (11% weight, c5 cap 8%,
    intact structural SOCLE). 11.1/8.0 = 1.39x cap < 1.5x -> rightsize normal
    (pas urgent). Doit retourner EXIT:HOLD + SIZE:RIGHTSIZE. Jamais l'un exempte
    l'autre. Cf [[conviction-grid-refonte-2026-06-24]] caps 8/6/4.5/3/2."""
    s = derive_steer(
        position_type="structural",
        erosion_verdict="INTACT",
        current_weight_pct=11.1,  # ASML reel
        conviction=5,             # cap 8% post-refonte
    )
    # EXIT : hold (these structurelle intacte / SOCLE gele)
    assert s.exit_policy.action == "hold"
    # SIZE : rightsize (over cap mais 11.1/8.0 = 1.39x < 1.5x -> normal pas urgent)
    assert s.size_action.action == "rightsize"
    assert s.size_action.over_cap_pp > 0
    # Trim qty calcule : ramene 11.1% a 8% -> ~-28% de qty
    assert s.size_action.target_qty_delta_pct < -20
    assert s.size_action.target_qty_delta_pct > -35


def test_critical_catch2_structural_intact_under_cap_no_size_action() -> None:
    """Memes inputs sauf weight 5% : cap c5 = 8% (refonte 24/06) donc sous cap -> no_action."""
    s = derive_steer("structural", "INTACT", current_weight_pct=5.0, conviction=5)
    assert s.exit_policy.action == "hold"
    assert s.size_action.action == "no_action"
    assert s.size_action.target_qty_delta_pct == 0.0


# ─── Test 4 : Sizing thresholds (cap c5=8% post-refonte 24/06) ───────────


def test_size_no_action_under_cap() -> None:
    s = derive_steer("priced", "INTACT", current_weight_pct=4.0, conviction=5)
    assert s.size_action.action == "no_action"


def test_size_no_action_exactly_at_cap() -> None:
    """Exactement au cap (8% post-refonte) = no_action (boundary inclusive sous le cap)."""
    s = derive_steer("priced", "INTACT", current_weight_pct=8.0, conviction=5)
    assert s.size_action.action == "no_action"
    assert s.size_action.over_cap_pp == 0.0


def test_size_rightsize_normal_zone() -> None:
    """Entre cap et 1.5x cap : rightsize normal (pas urgent).
    Cap c5 post-refonte = 8%, 1.5x = 12% -- weight 10% = entre cap et 1.5x."""
    s = derive_steer("priced", "INTACT", current_weight_pct=10.0, conviction=5)
    assert s.size_action.action == "rightsize"
    assert s.size_action.target_qty_delta_pct < 0


def test_size_urgent_rightsize_above_1_5x() -> None:
    """> 1.5x cap : urgent_rightsize.
    Cap c5 post-refonte = 8%, 1.5x = 12% -- weight 13% = 1.625x cap -> urgent."""
    s = derive_steer("priced", "INTACT", current_weight_pct=13.0, conviction=5)
    assert s.size_action.action == "urgent_rightsize"


# ─── Test 5 : Sizing independant du type ────────────────────────────────


@pytest.mark.parametrize("position_type", ["structural", "priced", "tactical"])
def test_size_action_invariant_across_types(position_type: str) -> None:
    """Meme weight + conviction -> meme SizeAction quel que soit le type.
    Refonte 24/06 : cap c5 = 8%, weight 13% = 1.625x -> urgent_rightsize uniforme."""
    s = derive_steer(position_type, "INTACT", current_weight_pct=13.0, conviction=5)
    assert s.size_action.action == "urgent_rightsize"
    assert s.size_action.cap_pct == 8.0
    assert s.size_action.over_cap_pp == 5.0


# ─── Test 6 : Sizing varie par conviction ────────────────────────────────


def test_size_uses_conviction_cap() -> None:
    """Cap c3 = 4.5% (refonte 24/06) -- weight 5% est over pour c3, sous pour c5 (cap 8%)."""
    s_c3 = derive_steer("priced", "INTACT", current_weight_pct=5.0, conviction=3)
    s_c5 = derive_steer("priced", "INTACT", current_weight_pct=5.0, conviction=5)
    assert s_c3.size_action.action == "rightsize"
    assert s_c5.size_action.action == "no_action"


# ─── Test 7 : INVALIDATION_HIT toujours exit_now quel que soit type ─────


@pytest.mark.parametrize("position_type", ["structural", "priced", "tactical"])
def test_invalidation_hit_always_exit_now(position_type: str) -> None:
    s = derive_steer(position_type, "INVALIDATION_HIT", 5.0, 5)
    assert s.exit_policy.action == "exit_now"
    assert "exit_full" in s.exit_policy.allowed


# ─── Test 8 : Type invalide ─────────────────────────────────────────────


def test_invalid_position_type_raises() -> None:
    with pytest.raises(ValueError, match="position_type invalide"):
        derive_steer("chokepoint", "INTACT", 5.0, 5)
    with pytest.raises(ValueError, match="position_type invalide"):
        derive_steer("", "INTACT", 5.0, 5)


def test_invalid_verdict_raises() -> None:
    with pytest.raises(ValueError, match="verdict invalide"):
        derive_steer("priced", "WHATEVER", 5.0, 5)


# ─── Test 9 : Verdict None graceful (jamais compute) ────────────────────


def test_verdict_none_treated_as_intact() -> None:
    """Verdict None (pas encore compute) -> traitement INTACT (defaut conservateur)."""
    s = derive_steer("structural", None, 5.0, 5)
    assert s.exit_policy.action == "hold"


# ─── Test 10 : Steer.display() format honnete ───────────────────────────


def test_display_shows_both_axes_separately() -> None:
    """Le display doit MONTRER LES 2 AXES SEPAREMENT (jamais fusionner).
    Refonte 24/06 : weight 13% sur cap c5=8% = 1.625x > 1.5x -> URGENT_RIGHTSIZE."""
    s = derive_steer("structural", "INTACT", 13.0, 5)
    out = s.display()
    assert "EXIT" in out
    assert "SIZE" in out
    assert "HOLD" in out  # exit action
    assert "URGENT_RIGHTSIZE" in out  # size action


# ─── Test 11 : Steer est frozen (no mutation) ───────────────────────────


def test_steer_frozen_no_mutation() -> None:
    """Steer + sous-classes sont @dataclass(frozen=True) -- immutables."""
    from dataclasses import FrozenInstanceError
    s = derive_steer("priced", "INTACT", 5.0, 5)
    with pytest.raises(FrozenInstanceError):
        s.exit_policy.action = "hacked"  # type: ignore[misc]


# ─── Test 12 : Smoke type Steer ─────────────────────────────────────────


def test_returns_steer_type() -> None:
    s = derive_steer("priced", "INTACT", 5.0, 5)
    assert isinstance(s, Steer)
