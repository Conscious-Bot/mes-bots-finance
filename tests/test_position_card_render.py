"""Carte-decision #1 etape 7 : tests render assembly + matrice fail-closed visuelle.

Verrouille :
- Bandeau fail-closed rouge visible si steer.bandeau non-vide
- Badge verdict 5-state couleur correcte (HOLD vert / TRIM ambre / EXIT rouge / REVIEW gris)
- Drift conviction inline si delta != 0 (masque sinon)
- Sections conditionnelles : structural_justification / discipline_flags / counter_argument
- Invalidation count fired surfaces depuis erosion_n_invalidation_hit
- Summary panel counters HOLD/TRIM/EXIT/REVIEW corrects

Tests isoles : appel direct _position_card(inputs, steer) avec mocks frozen.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from intelligence.card_inputs import CardInputs
from intelligence.card_steer import SteerOutput, SteerVerdict


class _FakeBookLine:
    """Stub BookLine pour les tests render."""
    def __init__(self, qty=4.0, current_price_eur=1462.20,
                 last_price_native=1462.20, last_price_currency="EUR",
                 price_asof="2026-06-07T18:00:00+00:00",
                 weight_market_eur=5849.0, avg_cost_eur=1150.0):
        self.qty = qty
        self.current_price_eur = current_price_eur
        self.last_price_native = last_price_native
        self.last_price_currency = last_price_currency
        self.price_asof = price_asof
        self.weight_market_eur = weight_market_eur
        self.avg_cost_eur = avg_cost_eur


def _mk_inputs(**overrides) -> CardInputs:
    """Factory CardInputs neutre (clean structural ASML c5)."""
    base = CardInputs(
        thesis_id=1,
        ticker="ASML.AS",
        thesis={
            "id": 1, "ticker": "ASML.AS", "conviction": 5,
            "direction": "long", "horizon": "5-7y",
            "opened_at": "2026-03-15T00:00:00+00:00",
            "last_reviewed": "2026-06-01T00:00:00+00:00",
            "entry_price": 1309.0,
            "target_partial": 1544.62,
            "target_full": 1806.42,
            "stop_price": None,
            "invalidation_triggers": [
                "Bookings <35B 2 Q consec",
                "Export restrictions extended",
            ],
        },
        position_type="structural",
        position_tags=["mega_cap"],
        structural_justification="Monopole EUV verified",
        conviction_current=5,
        conviction_at_entry=5,
        conviction_drift_delta=0,
        conviction_n_drifts=0,
        book_line=_FakeBookLine(),
        weight_pct=8.31,
        total_book_eur=52763.0,
        erosion_verdict=None,
        erosion_n_confirm=0, erosion_n_erode=0, erosion_n_invalidation_hit=0,
        cap_for_conviction_pct=6.0,
        ruin_budget_per_name_pct=1.5,
        allow_add_steer=False,
        price_asof_severity="green",
        thesis_review_age_days=6,
    )
    return replace(base, **overrides)


def _mk_steer(verdict=SteerVerdict.REVIEW, bandeau=None, **overrides) -> SteerOutput:
    base = SteerOutput(
        verdict=verdict,
        dominant_reason="test",
        bandeau=bandeau or [],
        exit_action="hold" if verdict == SteerVerdict.HOLD else None,
        size_action="no_action" if verdict == SteerVerdict.HOLD else None,
        target_qty_delta_pct=0.0,
        cap_pct=6.0,
    )
    return replace(base, **overrides)


def _render(inputs: CardInputs, steer: SteerOutput) -> str:
    """Import lazy : evite chargement render.py au collect time."""
    from dashboard.render import _position_card
    return _position_card(inputs, steer)


# ─── Test 1 : bandeau fail-closed visible si bandeau non-vide ────────────


def test_bandeau_fail_closed_visible_when_review() -> None:
    inputs = _mk_inputs(price_asof_severity="rouge")
    steer = _mk_steer(
        verdict=SteerVerdict.REVIEW,
        bandeau=["PRIX STALE (>4h SLA)"],
    )
    html = _render(inputs, steer)
    assert "FAIL-CLOSED L15" in html
    assert "PRIX STALE" in html
    # Bandeau rouge bg
    assert "#7a1f1f" in html


def test_bandeau_hidden_when_no_fail_closed() -> None:
    inputs = _mk_inputs()
    steer = _mk_steer(verdict=SteerVerdict.HOLD, bandeau=[])
    html = _render(inputs, steer)
    assert "FAIL-CLOSED L15" not in html


# ─── Test 2 : verdict badge 5-state couleurs ─────────────────────────────


@pytest.mark.parametrize("verdict, expected_label, expected_color", [
    (SteerVerdict.HOLD, "HOLD", "#3a9d4e"),         # vert
    (SteerVerdict.TRIM_TO_X, "TRIM", "#b8860b"),    # ambre, label canonique SPEC §1
    (SteerVerdict.EXIT, "EXIT", "#7a1f1f"),         # rouge
    (SteerVerdict.REVIEW, "REVIEW", "#666"),        # gris
])
def test_verdict_badge_color_matrix(verdict, expected_label, expected_color) -> None:
    inputs = _mk_inputs()
    steer = _mk_steer(verdict=verdict)
    html = _render(inputs, steer)
    # Le badge contient le label canonique (vocab SPEC_ALERT_VOCABULARY §1 :
    # TRIM_TO_X / ADD_TO_X -> TRIM / ADD, pas l'enum brut) + la couleur.
    assert f"▶ {expected_label}" in html
    assert expected_color in html


# ─── Test 3 : drift conviction visible si delta != 0 ─────────────────────


def test_drift_visible_when_delta_nonzero() -> None:
    inputs = _mk_inputs(
        conviction_current=3,
        conviction_at_entry=5,
        conviction_drift_delta=-2,
        conviction_n_drifts=1,
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "drift" in html
    assert "PIT c5" in html or "c5" in html
    assert "now c3" in html or "→ now c3" in html


def test_drift_hidden_when_delta_zero() -> None:
    inputs = _mk_inputs(conviction_drift_delta=0)
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "pc-drift" not in html  # class hidden


# ─── Test 4 : sections conditionnelles ───────────────────────────────────


def test_structural_justification_section_visible_for_structural() -> None:
    inputs = _mk_inputs(
        position_type="structural",
        structural_justification="Monopole EUV verified",
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "STRUCTURAL JUSTIFICATION" in html
    assert "Monopole EUV verified" in html


def test_priced_does_not_show_structural_section() -> None:
    inputs = _mk_inputs(
        position_type="priced",
        structural_justification=None,
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "STRUCTURAL JUSTIFICATION" not in html


def test_discipline_flags_hidden_when_none() -> None:
    """0 flags actifs -> section invisible."""
    inputs = _mk_inputs(
        kill_status="dormant",
        over_cap_status="dormant",
        bias_events_open=[],
        ballast_membership=False,
        conviction_n_drifts=0,
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "DISCIPLINE FLAGS" not in html


def test_discipline_flags_visible_with_active() -> None:
    inputs = _mk_inputs(
        kill_status="at_risk",
        over_cap_status="over",
        over_cap_pct=8.5,
        bias_events_open=[{"bias": "fomo_greed"}],
        ballast_membership=True,
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "DISCIPLINE FLAGS" in html
    assert "KILL_CRITERIA" in html
    assert "OVER_CAP" in html
    assert "BIAS_OPEN" in html
    assert "BALLAST" in html


def test_counter_argument_visible_when_present() -> None:
    inputs = _mk_inputs(
        counter_argument_brief="Concurrent EUV emerge plus tot que prevu",
        counter_argument_pressure_score=7,
        counter_argument_at="2026-05-29T10:00:00+00:00",
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "CONTRE-ARGUMENT" in html
    assert "Concurrent EUV emerge plus tot que prevu" in html
    assert "pressure 7" in html


def test_counter_argument_hidden_when_absent() -> None:
    inputs = _mk_inputs(counter_argument_brief=None)
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "CONTRE-ARGUMENT" not in html


# ─── Test 5 : invalidation count fired ───────────────────────────────────


def test_invalidation_count_fired_surfaces() -> None:
    """Si erosion_n_invalidation_hit > 0, count visible."""
    inputs = _mk_inputs(erosion_n_invalidation_hit=2)
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "INVALIDATION TRIGGERS (2/2 fired)" in html


def test_invalidation_count_zero_default() -> None:
    inputs = _mk_inputs(erosion_n_invalidation_hit=0)
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "INVALIDATION TRIGGERS (0/2 fired)" in html


# ─── Test 6 : what-changed avec classifications ──────────────────────────


def test_what_changed_top5_with_classifications() -> None:
    classifications = [
        {
            "signal_id": i, "bears_on": "driver", "target_index": 0,
            "relation": ("confirms" if i % 2 == 0 else "erodes"),
            "confidence": 0.8, "materiality": 3.0 - i * 0.2,
            "rationale": f"rat{i}", "evidence_quote": f"quote{i}",
        }
        for i in range(8)  # 8 classifications, top-5 affichees
    ]
    inputs = _mk_inputs(
        erosion_verdict="INTACT",
        erosion_classifications=classifications,
    )
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "WHAT CHANGED SINCE ENTRY" in html
    assert "top-5/8" in html


def test_what_changed_empty_when_no_compute() -> None:
    """Si verdict None ET classifications vides, section signale l'absence
    de classifications persistees. Cure visuelle 12/06 : prose "non compute"
    remplacee par message explicite "aucune classification persistee" +
    chip PENDING sur le verdict header (cf cure section EROSION_DETECTED)."""
    inputs = _mk_inputs(erosion_verdict=None, erosion_classifications=[])
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "WHAT CHANGED SINCE ENTRY" in html
    assert "aucune classification persistee" in html
    # Chip PENDING dans le verdict header (cure visuelle 12/06)
    assert "pc-verdict-pending" in html


# ─── Test 7 : structural asymmetry honest (Catch 3) ──────────────────────


def test_structural_asymmetry_shows_structural_not_infinity() -> None:
    inputs = _mk_inputs(position_type="structural")
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "STRUCTUREL non-borne par prix" in html
    assert "n/a (axe structural" in html
    # PAS de "∞" ou "infinity" ou ratio infini menteur
    assert "ratio: ∞" not in html
    assert "ratio infini" not in html


# ─── Test 8 : tags visibles ─────────────────────────────────────────────


def test_tags_visible_in_header() -> None:
    inputs = _mk_inputs(position_tags=["mega_cap", "satellite"])
    steer = _mk_steer()
    html = _render(inputs, steer)
    assert "mega_cap" in html
    assert "satellite" in html


def test_no_tags_shows_dash() -> None:
    inputs = _mk_inputs(position_tags=[])
    steer = _mk_steer()
    html = _render(inputs, steer)
    # tags cell shows mdash when empty
    assert "&mdash;" in html
