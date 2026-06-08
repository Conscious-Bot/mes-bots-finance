"""Tests verrouillants SOCLE Phase 3 : PositionView une-compute-deux-rendus.

L'INVARIANT CENTRAL : tout nombre present dans row ET card est byte-identique.
test_byte_identity_ratio_row_and_card tue le bug fondateur 0,5x (page) vs 1,80x
(card) sur le meme ticker.

Walking-skeleton : 4063.T (Shin-Etsu, JPY native) traverse le pipeline complet
prix-Datum -> derive value_eur -> compute_position -> project_row, avec assert
byte-identite + fail-closed propage si prix stale.

Cf SPEC_POSITIONS_CARD_LINK.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import pytest

from shared.datum import Datum
from shared.position_view import (
    PositionView,
    RowView,
    _compute_asym_ratio,
    compute_position,
    project_row,
)

# === Fixtures : doubles minimalistes de CardInputs + SteerOutput =========


class FakeVerdict(StrEnum):
    HOLD = "hold"
    TRIM = "trim"
    REVIEW = "review"


@dataclass
class FakeSteer:
    verdict: FakeVerdict = FakeVerdict.HOLD
    dominant_reason: str = "no signal"
    bandeau: list[str] = None  # type: ignore[assignment]
    exit_action: str | None = None
    size_action: str | None = None
    target_qty_delta_pct: float = 0.0
    cap_pct: float | None = None


@dataclass
class FakeCardInputs:
    thesis_id: int = 1
    ticker: str = "4063.T"
    thesis: dict = None  # type: ignore[assignment]
    # Note : 4063.T (Shin-Etsu) est priced/tactical ici pour exercer le ratio
    # chiffre. La position structural exception est testee separement.
    position_type: str = "priced"
    position_tags: list[str] = None  # type: ignore[assignment]
    structural_justification: str | None = None
    conviction_current: int = 4
    conviction_at_entry: int = 4
    erosion_verdict: str | None = "intact"
    over_cap_status: str | None = None
    bias_events_open: list = None  # type: ignore[assignment]


def _shin_etsu_thesis() -> dict:
    """Fixture realiste 4063.T : Shin-Etsu Chemical, JPY native."""
    return {
        "name": "Shin-Etsu Chemical",
        "entry_native": 5800.0,
        "target_partial_native": 7000.0,
        "target_full_native": 8500.0,
        "stop_native": 4900.0,
    }


def _build_ci(**overrides) -> FakeCardInputs:
    ci = FakeCardInputs()
    ci.thesis = _shin_etsu_thesis()
    ci.position_tags = []
    ci.bias_events_open = []
    for k, v in overrides.items():
        setattr(ci, k, v)
    return ci


def _build_price_datum(value: float = 6800.0, degraded: bool = False) -> Datum:
    return Datum(
        value=value,
        asof=datetime.now(UTC).isoformat(),
        source="yfinance:4063.T",
        confidence=1.0 if not degraded else 0.4,
        degraded=degraded,
    )


def _build_fx_datum(value: float = 0.0061, degraded: bool = False) -> Datum:
    """JPY -> EUR (~0.0061 = 1 JPY = 0.0061 EUR)."""
    return Datum(
        value=value,
        asof=datetime.now(UTC).isoformat(),
        source="yfinance:fx:JPY-EUR",
        confidence=1.0 if not degraded else 0.4,
        degraded=degraded,
    )


def _build_value_eur_datum(value: float = 414800.0, degraded: bool = False) -> Datum:
    """qty=10, price=6800 JPY, fx=0.0061 -> 414.8 EUR (small position) ; ici test marker."""
    return Datum(
        value=value,
        asof=datetime.now(UTC).isoformat(),
        source="derived",
        confidence=1.0 if not degraded else 0.4,
        degraded=degraded,
    )


# === Test 1 : _compute_asym_ratio (la primitive du ratio canonique) ====


def test_asym_ratio_favorable_thesis_from_entry() -> None:
    """4063.T thesis : entry 5800 JPY, target_full 8500, stop 4900.

    Convention canonique (depuis ENTRY, pas price actuel) :
      upside = (8500/5800 - 1) * 100 = 46.55%
      downside = (4900/5800 - 1) * 100 = -15.52%
      ratio = (8500-5800) / (5800-4900) = 2700/900 = 3.0x (favorable)

    C'est le ratio thesis-level (stable tant que la these tient).
    Pas le ratio "asymetrie de position actuelle depuis prix".
    """
    upside, downside, ratio = _compute_asym_ratio(
        entry=5800.0, target_partial=7000.0, target_full=8500.0, stop=4900.0
    )
    assert upside == pytest.approx(46.55, abs=0.5)
    assert downside == pytest.approx(-15.52, abs=0.5)
    assert ratio == pytest.approx(3.0, abs=0.05)


def test_asym_ratio_returns_none_if_missing_inputs() -> None:
    """entry/stop/target manquants -> (None, None, None) (fail-closed)."""
    assert _compute_asym_ratio(None, 10.0, 20.0, 5.0) == (None, None, None)
    assert _compute_asym_ratio(15.0, None, None, 5.0) == (None, None, None)
    assert _compute_asym_ratio(15.0, 20.0, None, None) == (None, None, None)


def test_asym_ratio_none_if_entry_equals_stop() -> None:
    """entry == stop -> denominateur 0 -> ratio non-defini."""
    _upside, _downside, ratio = _compute_asym_ratio(
        entry=5000.0, target_partial=7000.0, target_full=8500.0, stop=5000.0
    )
    assert ratio is None


# === Test 2 : compute_position assemble correctement ===================


def test_compute_position_builds_view_from_4063t_walking_skeleton() -> None:
    """Walking-skeleton STRICT : 4063.T traverse le pipeline complet.

    prix-Datum 6800 JPY + fx-Datum 0.0061 + value_eur-Datum 414800 EUR
    -> CardInputs (these Shin-Etsu, structural, conv 4)
    -> SteerOutput (HOLD, intact thesis)
    -> compute_position -> PositionView
    """
    ci = _build_ci()
    steer = FakeSteer(bandeau=[])
    price = _build_price_datum()
    fx = _build_fx_datum()
    value_eur = _build_value_eur_datum()

    view = compute_position(
        thesis_id=ci.thesis_id,
        card_inputs=ci,
        steer_output=steer,
        price_datum=price,
        fx_datum=fx,
        value_eur_datum=value_eur,
    )
    assert view.ticker == "4063.T"
    assert view.name == "Shin-Etsu Chemical"
    assert view.position_type == "priced"
    assert view.conviction == 4
    assert view.price_native == 6800.0
    assert view.fx_rate == 0.0061
    # Asymetrie thesis-level : ratio depuis entry (5800), pas price (6800)
    # entry=5800, target_full=8500, stop=4900 -> ratio = 2700/900 = 3.0x favorable
    assert view.asym_ratio is not None
    assert view.asym_ratio == pytest.approx(3.0, abs=0.05)
    # Steer
    assert view.steer_verdict == "hold"
    # Lineage capture (Merkle-DAG seed)
    assert len(view.inputs_lineage_ids) == 3  # value_eur + price + fx ids
    assert view.degraded is False


# === Test 2.5 : position structural -> ratio n/a (downside non-borne par prix) ===


def test_structural_position_has_no_ratio() -> None:
    """Catch 3 render.py:2293 : structural -> downside non-borne par prix.

    Convention canonique : pour structural, asym_ratio = None ; upside_pct
    est calcule depuis target_full/entry, mais downside_pct = None (axe
    structural != axe prix). Le caller affiche "n/a" sur le ratio.
    """
    ci = _build_ci(position_type="structural")
    steer = FakeSteer(bandeau=[])
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    assert view.position_type == "structural"
    assert view.asym_ratio is None  # ratio n/a pour structural
    assert view.downside_pct is None  # non-borne par prix
    # upside_pct existe (depuis target/entry, sans axe prix)
    assert view.upside_pct is not None


# === Test 3 : LE TEST QUI TUE LE BUG (byte-identite ligne/card) =========


def test_byte_identity_ratio_row_and_card_4063t() -> None:
    """L'invariant fondateur : asym_ratio dans row == asym_ratio dans card.

    Avant ce SPEC, render.py derivait le ratio 2 fois (un calcul pour la
    ligne, un autre pour la card) -> divergence visible (0.5x rouge vs
    1.80x favorable). Avec PositionView source unique, project_row ne
    fait QUE projeter : aucune chance de divergence par construction.
    """
    ci = _build_ci()
    steer = FakeSteer(bandeau=[])
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    row = project_row(view)

    # Le test qui tue : memes nombres, byte-identiques (id Python ==)
    assert row.asym_ratio == view.asym_ratio
    assert row.price_native == view.price_native
    assert row.value_eur == (view.value_eur_datum.value if view.value_eur_datum else None)
    assert row.ticker == view.ticker
    assert row.position_type == view.position_type
    assert row.erosion_verdict == view.erosion_verdict
    assert row.degraded == view.degraded


# === Test 4 : chip vient du steer, jamais d'un calcul ligne ============


def test_chip_in_row_comes_from_steer_not_local_calc() -> None:
    """Chip dans row = steer.chip (None si pas act, value si act-class)."""
    ci = _build_ci()
    # Steer avec exit_action -> chip = exit_action (TRIM par exemple)
    steer = FakeSteer(
        verdict=FakeVerdict.TRIM,
        dominant_reason="weight > cap",
        bandeau=[],
        exit_action="TRIM",
        size_action="reduce_to_cap",
    )
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    row = project_row(view)
    # exit_action prioritaire pour chip
    assert view.steer_chip == "TRIM"
    assert row.steer_chip == view.steer_chip


def test_chip_silent_when_steer_calm() -> None:
    """Steer HOLD/WATCH (calm-class) -> aucune chip (silence par defaut)."""
    ci = _build_ci()
    steer = FakeSteer(
        verdict=FakeVerdict.HOLD,
        dominant_reason="thesis intact, no signal",
        bandeau=[],
        exit_action=None,
        size_action=None,
    )
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    row = project_row(view)
    assert view.steer_chip is None
    assert row.steer_chip is None


# === Test 5 : fail-closed propage (Datum.degraded -> view.degraded) =====


def test_degraded_propagates_when_price_stale() -> None:
    """Price Datum degraded (stale au-dela SLA) -> value_eur degraded -> view.degraded.

    Le test de propagation : la bannière fail-closed n'est pas cosmétique,
    elle dégrade les nombres dépendants.
    """
    ci = _build_ci()
    steer = FakeSteer(bandeau=[])
    # Value_eur derive d'un prix stale -> Datum.degraded propage
    stale_value = _build_value_eur_datum(degraded=True)
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(degraded=True),
        fx_datum=_build_fx_datum(),
        value_eur_datum=stale_value,
    )
    assert view.degraded is True
    assert view.degraded_reason is not None
    # Row herite aussi
    row = project_row(view)
    assert row.degraded is True


def test_degraded_if_value_eur_none() -> None:
    """Pas de value_eur (fetch fail ou L15 rouge) -> view.degraded=True."""
    ci = _build_ci()
    steer = FakeSteer(bandeau=[])
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=None, fx_datum=None,
        value_eur_datum=None,
    )
    assert view.degraded is True
    assert "unavailable" in (view.degraded_reason or "")


# === Test 6 : discipline flags (vocabulary FLAG class) ==================


def test_discipline_flags_include_over_cap_and_bias_open() -> None:
    ci = _build_ci(over_cap_status="over", bias_events_open=[{"id": 1}])
    steer = FakeSteer(bandeau=[])
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    assert "OVER_CAP" in view.discipline_flags
    assert "BIAS_OPEN" in view.discipline_flags


def test_no_stop_no_target_flags() -> None:
    """Thesis sans stop ni target -> flags NO_STOP + NO_TARGET."""
    ci = _build_ci()
    ci.thesis = {"name": "Test", "entry_native": 100.0}  # pas de stop/target
    steer = FakeSteer(bandeau=[])
    view = compute_position(
        thesis_id=1,
        card_inputs=ci,
        steer_output=steer,
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    assert "NO_STOP" in view.discipline_flags
    assert "NO_TARGET" in view.discipline_flags


# === Test 7 : PositionView frozen (anti-tampering) ======================


def test_position_view_is_frozen() -> None:
    view = compute_position(
        thesis_id=1, card_inputs=_build_ci(), steer_output=FakeSteer(bandeau=[]),
        price_datum=_build_price_datum(), fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    with pytest.raises((AttributeError, TypeError)):
        view.asym_ratio = 999.99  # type: ignore[misc]


def test_row_view_is_frozen() -> None:
    view = compute_position(
        thesis_id=1, card_inputs=_build_ci(), steer_output=FakeSteer(bandeau=[]),
        price_datum=_build_price_datum(), fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    row = project_row(view)
    with pytest.raises((AttributeError, TypeError)):
        row.asym_ratio = 999.99  # type: ignore[misc]


# === Test 8 : lineage capture (Merkle-DAG seed) =========================


def test_inputs_lineage_ids_captured() -> None:
    """Le SOCLE Phase 0 a pose le content-hash ; PositionView capture les
    ids des Datums sources -> seed du graphe vivant.
    """
    view = compute_position(
        thesis_id=1, card_inputs=_build_ci(), steer_output=FakeSteer(bandeau=[]),
        price_datum=_build_price_datum(),
        fx_datum=_build_fx_datum(),
        value_eur_datum=_build_value_eur_datum(),
    )
    # 3 Datums : value_eur, price, fx
    assert len(view.inputs_lineage_ids) == 3
    # Chaque id est un sha256 hex 64 chars
    for did in view.inputs_lineage_ids:
        assert len(did) == 64
