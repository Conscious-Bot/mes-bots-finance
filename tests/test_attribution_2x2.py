"""Tests B DECISION_QUALITY_ENGINE : attribution causale 2x2.

Verrouille la doctrine "scorer la decision pas le resultat" :
- 4 quadrants happy path (SKILL, LUCK, SOUND_PROCESS, LEARNING)
- 5e quadrant L15 fail-closed (UNATTRIBUTABLE) si residu domine
- luck_share aggregate = vrai taux d'illusion de skill
- quadrant_counts pour dashboard surface

Le test CRITIQUE : LUCK distinct de SKILL meme avec outcome positif identique.
Sans ce gating, calibration sur outcomes seule = aveugle au quadrant qui ruine.
"""

from __future__ import annotations

from track_record.attribution import (
    EntryView,
    EpicDriver,
    Quadrant,
    RealizedView,
    ReturnDecomposition,
    attribute_decision,
    luck_share,
    quadrant_counts,
)


def _make_entry(
    direction="up", magnitude=150.0, price_channel="fundamental"
) -> EntryView:
    return EntryView(
        thesis_id=1, ticker="NVDA", conviction=4,
        epic_driver=EpicDriver(
            kpi="gross_margin_bps",
            direction=direction,
            magnitude=magnitude,
            price_channel=price_channel,
        ),
        benchmark_ticker="SPY",
        entry_ts="2026-01-01T00:00:00Z",
    )


def _make_realized(
    kpi_move_dir="up",
    kpi_move=200.0,
    fundamental=0.10,
    multiple=0.02,
    residual=0.01,
    kill_criteria_respected=True,
    excess_return=0.08,
    outperf_threshold=0.0,
) -> RealizedView:
    return RealizedView(
        kpi_move_dir=kpi_move_dir,
        kpi_move=kpi_move,
        return_decomposition=ReturnDecomposition(
            fundamental=fundamental, multiple=multiple, residual=residual,
        ),
        kill_criteria_respected=kill_criteria_respected,
        excess_return=excess_return,
        outperf_threshold=outperf_threshold,
    )


# === Test 1 : SKILL (reason right + outcome good) =========================


def test_skill_quadrant_when_all_aligned():
    """Driver hit + channel dominant matche + kill_criteria respected + outcome bon."""
    entry = _make_entry(price_channel="fundamental")
    # fundamental = 0.10 dominant, multiple = 0.02, residual = 0.01
    realized = _make_realized()
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.SKILL
    assert result["driver_hit"] is True
    assert result["attributed_channel"] == "fundamental"
    assert result["reason_right"] is True
    assert result["outcome_good"] is True


# === Test 2 : LUCK (le quadrant qui ruine) ================================


def test_luck_quadrant_outcome_good_but_wrong_reason():
    """Outcome positif IDENTIQUE a SKILL mais raison fausse : channel
    dominant != price_channel declare. Le quadrant qui ruine.

    Sans ce gate, P&L positif = "skill confirme". Verite : chance.
    """
    entry = _make_entry(price_channel="fundamental")
    # excess_return positif mais le mouvement vient du MULTIPLE (re-rating),
    # pas du fundamental que tu avais predit
    realized = _make_realized(
        fundamental=0.01, multiple=0.10, residual=0.02,  # multiple dominant
        excess_return=0.08,  # toujours bon outcome
    )
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.LUCK
    assert result["attributed_channel"] == "multiple"
    assert result["outcome_good"] is True
    assert result["reason_right"] is False  # channel != price_channel declare


def test_luck_quadrant_driver_missed_but_outcome_good():
    """KPI n'a pas bouge comme predit mais le prix a monte quand meme."""
    entry = _make_entry(direction="up", magnitude=200.0)
    realized = _make_realized(
        kpi_move_dir="up", kpi_move=50.0,  # bouge dans le bon sens mais magnitude insuffisante
        excess_return=0.08,
    )
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.LUCK
    assert result["driver_hit"] is False


# === Test 3 : SOUND_PROCESS (reason right + outcome bad) ==================


def test_sound_process_quadrant_outcome_negative_but_reasoning_correct():
    """Driver hit + channel dominant matche + kill_criteria OK + outcome NEG.
    Process sain qui rencontre vol. NE PAS desapprendre.
    """
    entry = _make_entry(price_channel="fundamental")
    realized = _make_realized(
        fundamental=0.05, multiple=0.01, residual=0.01,  # fundamental dominant
        excess_return=-0.03,  # outcome mauvais
    )
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.SOUND_PROCESS
    assert result["reason_right"] is True
    assert result["outcome_good"] is False


# === Test 4 : LEARNING (reason wrong + outcome bad) =======================


def test_learning_quadrant_outcome_bad_and_wrong_reason():
    """Driver miss + channel different + outcome neg. Vrai apprentissage."""
    entry = _make_entry(direction="up", magnitude=200.0, price_channel="fundamental")
    realized = _make_realized(
        kpi_move_dir="down", kpi_move=-50.0,  # driver miss complet
        fundamental=0.01, multiple=-0.04, residual=0.005,  # multiple dominant negatif
        excess_return=-0.05,
    )
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.LEARNING
    assert result["driver_hit"] is False
    assert result["outcome_good"] is False


# === Test 5 : UNATTRIBUTABLE (L15 fail-closed) ============================


def test_unattributable_when_residual_dominates():
    """residual >= 50% du sum(abs(decomp)) -> UNATTRIBUTABLE."""
    entry = _make_entry()
    realized = _make_realized(
        fundamental=0.02, multiple=0.01, residual=0.10,  # residual domine clairement
        excess_return=0.08,
    )
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.UNATTRIBUTABLE
    assert "residual" in result["unattributable_reason"]


def test_unattributable_blocks_fabricated_skill():
    """Si residual domine MEME avec outcome positif et driver hit, on REFUSE
    de fabriquer une cause SKILL. C'est L15 applique a la decision quality.
    """
    entry = _make_entry(price_channel="fundamental")
    realized = _make_realized(
        kpi_move="up", kpi_move_dir="up",  # driver theoriquement hit
        fundamental=0.03, multiple=0.02, residual=0.10,  # residual domine
        excess_return=0.10,  # outcome bon
    )
    result = attribute_decision(entry, realized)
    assert result["quadrant"] == Quadrant.UNATTRIBUTABLE
    # Pas de "SKILL fabrique" alors qu'on ne sait pas pourquoi ca a marche


# === Test 6 : kill_criteria_respected gate dans reason_right ==============


def test_kill_criteria_violation_demotes_to_luck():
    """Driver hit + channel dominant matche MAIS kill_criteria viole ->
    reason_right = False. Process casse meme si KPI ok.
    """
    entry = _make_entry(price_channel="fundamental")
    realized = _make_realized(
        fundamental=0.10, multiple=0.02, residual=0.01,
        kill_criteria_respected=False,  # process casse
        excess_return=0.08,
    )
    result = attribute_decision(entry, realized)
    # Reason right requires kill_criteria_respected -> demoted to LUCK
    assert result["quadrant"] == Quadrant.LUCK
    assert result["reason_right"] is False


# === Test 7 : luck_share aggregate ========================================


def test_luck_share_zero_when_only_skill():
    attrs = [
        {"quadrant": Quadrant.SKILL},
        {"quadrant": Quadrant.SKILL},
        {"quadrant": Quadrant.LEARNING},  # outcome bad ignore
    ]
    assert luck_share(attrs) == 0.0


def test_luck_share_half_when_skill_and_luck_equal():
    attrs = [
        {"quadrant": Quadrant.SKILL},
        {"quadrant": Quadrant.LUCK},
        {"quadrant": Quadrant.LEARNING},  # bad outcome ignore
        {"quadrant": Quadrant.SOUND_PROCESS},  # bad outcome ignore
    ]
    assert luck_share(attrs) == 0.5


def test_luck_share_none_when_no_good_outcomes():
    """Pas de SKILL ni LUCK -> N_good = 0 -> None (L15 gating)."""
    attrs = [
        {"quadrant": Quadrant.LEARNING},
        {"quadrant": Quadrant.SOUND_PROCESS},
        {"quadrant": Quadrant.UNATTRIBUTABLE},
    ]
    assert luck_share(attrs) is None


def test_luck_share_one_when_all_luck():
    """100% des outcomes positifs sont de la chance -> illusion de skill totale."""
    attrs = [
        {"quadrant": Quadrant.LUCK},
        {"quadrant": Quadrant.LUCK},
        {"quadrant": Quadrant.LEARNING},  # ignore
    ]
    assert luck_share(attrs) == 1.0


# === Test 8 : quadrant_counts aggregate ===================================


def test_quadrant_counts_per_quadrant():
    attrs = [
        {"quadrant": Quadrant.SKILL},
        {"quadrant": Quadrant.SKILL},
        {"quadrant": Quadrant.LUCK},
        {"quadrant": Quadrant.UNATTRIBUTABLE},
    ]
    counts = quadrant_counts(attrs)
    assert counts["right_reason_right_outcome"] == 2  # SKILL
    assert counts["wrong_reason_right_outcome"] == 1  # LUCK
    assert counts["unattributable"] == 1
    assert counts["right_reason_wrong_outcome"] == 0  # SOUND_PROCESS
    assert counts["wrong_reason_wrong_outcome"] == 0  # LEARNING
