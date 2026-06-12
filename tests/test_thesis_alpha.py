"""Tests verrouillants SPEC_THESIS_ALPHA_RESOLVER §5 (helpers purs).

Couverture :
- A1 convert_at_asof_freezes_fx — fx_asof figé par caller, pas de drift
- A2 convert_no_op_when_currencies_match — devises identiques → fx=1.0 forcé
- D1 alpha_native_strippe_fx — formule alpha en native, indépendant fx live
- F1-F4 fail-closed sur inputs invalides (PT manquant, fx invalide, NaN/Inf)
- C1 classify edge cases (sign égal, sign opposé, ε neutre, signes nuls)
- Bonus your_delta + alpha cohérents par construction (asof_price partagé)
"""

from __future__ import annotations

from datetime import date

import pytest

from shared.thesis_alpha import (
    classify_direction,
    compute_alpha_realized_pct,
    compute_your_delta_native_pct,
    convert_consensus_pt_to_native,
)

# ============================================================
# A1 — Convert at asof freezes fx (décision A)
# ============================================================


def test_a1_convert_at_asof_freezes_fx():
    """fx_asof passé par caller est utilisé tel quel, pas re-fetché."""
    consensus = {"pt": 1690.0, "median": 1730.0, "currency": "USD", "asof": date(2026, 6, 10)}
    # ASML.AS exemple : consensus USD, native EUR, fx_asof 0.8657 (USD→EUR)
    result = convert_consensus_pt_to_native(consensus, native_currency="EUR", fx_at_asof=0.8657)
    assert result is not None
    assert result["pt_native"] == pytest.approx(1690.0 * 0.8657)
    assert result["median_native"] == pytest.approx(1730.0 * 0.8657)
    assert result["fx_at_asof_used"] == 0.8657
    assert result["asof"] == date(2026, 6, 10)
    assert result["source_currency"] == "USD"
    assert result["native_currency"] == "EUR"


def test_a1_convert_uses_caller_fx_even_if_stale():
    """Même si le caller passe un fx 'périmé', le helper l'utilise tel quel.

    C'est le contrat : asof fige le mètre. Le caller est responsable de
    fetcher fx_at_asof correct via prices.get_fx_rate_on(currency, native, asof).
    """
    consensus = {"pt": 100.0, "median": 100.0, "currency": "USD", "asof": date(2025, 1, 1)}
    # Caller passe un fx historique vieux (2025-01-01 par exemple)
    result = convert_consensus_pt_to_native(consensus, native_currency="EUR", fx_at_asof=0.92)
    assert result["pt_native"] == pytest.approx(92.0)


# ============================================================
# A2 — No-op when currencies match (décision A2)
# ============================================================


def test_a2_no_op_when_currencies_match():
    """Si consensus.currency == native_currency, fx forcé à 1.0 (override)."""
    consensus = {"pt": 1730.0, "median": 1690.0, "currency": "EUR", "asof": date(2026, 6, 10)}
    result = convert_consensus_pt_to_native(consensus, native_currency="EUR", fx_at_asof=0.8657)
    assert result is not None
    # Même si fx_at_asof=0.8657 passé, override à 1.0 (no-op contrat)
    assert result["fx_at_asof_used"] == 1.0
    assert result["pt_native"] == 1730.0
    assert result["median_native"] == 1690.0


def test_a2_no_op_for_sk_hynix_krw():
    """SK Hynix : consensus KRW + ticker KRW → fx=1.0, conversion no-op.

    Le seul prérequis SK = poser le PT (la devise n'est pas le souci).
    """
    consensus = {"pt": 2300000.0, "median": 2300000.0, "currency": "KRW", "asof": date(2026, 6, 10)}
    result = convert_consensus_pt_to_native(consensus, native_currency="KRW", fx_at_asof=99.99)
    assert result["pt_native"] == 2300000.0
    assert result["fx_at_asof_used"] == 1.0


# ============================================================
# D1 — Alpha native strippé fx (décision D)
# ============================================================


def test_d1_alpha_native_strippe_fx():
    """Alpha en native, indépendant du fx live entre asof et resolve.

    Setup : action US, asof_price=100 USD, resolve_price=110 USD,
    pt_consensus 105 USD → pt_native_asof=105 USD (devises matchent).

    Alpha attendu : (110-105)/100 × 100 = +5% native USD.
    Le fx EUR/USD à resolve peut être n'importe quoi — l'alpha ne le voit pas.
    """
    consensus = {"pt": 105.0, "median": 105.0, "currency": "USD", "asof": date(2026, 6, 10)}
    pr = convert_consensus_pt_to_native(consensus, native_currency="USD", fx_at_asof=1.0)
    pt_native = pr["pt_native"]
    assert pt_native == 105.0

    alpha = compute_alpha_realized_pct(
        resolve_price_native=110.0,
        pt_native_asof=pt_native,
        asof_price_native=100.0,
    )
    assert alpha == pytest.approx(5.0)


def test_d1_your_delta_and_alpha_share_denominator():
    """your_delta et alpha partagent asof_price → leur sign est comparable.

    SK Hynix exemple : asof_price=2_077_000 KRW, ta full=3_800_000 KRW,
    pt_native_asof=2_300_000 KRW (consensus moyen blended).

    your_delta = (3.8M - 2.3M)/2.077M × 100 = +72.2% (bull thesis)
    Si à 12m resolve_price=3.0M : alpha = (3.0M - 2.3M)/2.077M × 100 = +33.7%
    Sign égal (les deux > 0) → 'correct'.
    """
    asof_price = 2_077_000.0
    pt_native = 2_300_000.0
    your_target = 3_800_000.0

    your_delta = compute_your_delta_native_pct(your_target, pt_native, asof_price)
    assert your_delta > 0  # bull thesis

    alpha = compute_alpha_realized_pct(
        resolve_price_native=3_000_000.0, pt_native_asof=pt_native, asof_price_native=asof_price,
    )
    assert alpha > 0  # action a battu le PT consensus

    direction = classify_direction(your_delta, alpha)
    assert direction == "correct"


def test_d1_alpha_negative_when_action_misses_pt():
    """Action qui rate le PT : alpha négatif. Si bull thesis → 'incorrect'."""
    asof_price = 100.0
    pt_native = 110.0
    your_target = 130.0  # bull, beaucoup au-dessus du PT
    # 12m : resolve à 95 (loin sous PT)
    alpha = compute_alpha_realized_pct(95.0, pt_native, asof_price)
    your_delta = compute_your_delta_native_pct(your_target, pt_native, asof_price)
    assert alpha < 0
    assert your_delta > 0
    assert classify_direction(your_delta, alpha) == "incorrect"


# ============================================================
# F — Fail-closed L15 (consensus_ref, fx, PT invalides)
# ============================================================


def test_f1_returns_none_when_consensus_ref_none():
    assert convert_consensus_pt_to_native(None, "EUR", 0.86) is None
    assert convert_consensus_pt_to_native({}, "EUR", 0.86) is None


def test_f2_returns_none_when_pt_missing_or_invalid():
    base = {"median": 100.0, "currency": "USD", "asof": date(2026, 6, 10)}
    # pt manquant
    assert convert_consensus_pt_to_native(base, "EUR", 0.86) is None
    # pt nul / négatif
    assert convert_consensus_pt_to_native({**base, "pt": 0}, "EUR", 0.86) is None
    assert convert_consensus_pt_to_native({**base, "pt": -100}, "EUR", 0.86) is None
    # pt NaN
    assert convert_consensus_pt_to_native({**base, "pt": float("nan")}, "EUR", 0.86) is None


def test_f3_returns_none_when_fx_invalid_and_currencies_differ():
    consensus = {"pt": 100.0, "median": 100.0, "currency": "USD", "asof": date(2026, 6, 10)}
    # fx nul / négatif (devises diffèrent donc fx EST utilisé)
    assert convert_consensus_pt_to_native(consensus, "EUR", 0.0) is None
    assert convert_consensus_pt_to_native(consensus, "EUR", -0.5) is None
    # fx NaN / Inf
    assert convert_consensus_pt_to_native(consensus, "EUR", float("nan")) is None
    assert convert_consensus_pt_to_native(consensus, "EUR", float("inf")) is None


def test_f4_alpha_helpers_fail_closed_on_invalid_inputs():
    # NaN / Inf en input
    assert compute_your_delta_native_pct(float("nan"), 100, 100) is None
    assert compute_alpha_realized_pct(100, float("inf"), 100) is None
    # asof_price <= 0 (division par zéro / négatif sans sens)
    assert compute_your_delta_native_pct(110, 100, 0) is None
    assert compute_alpha_realized_pct(110, 100, -50) is None


# ============================================================
# C — Classify direction edge cases
# ============================================================


def test_c1_classify_neutral_when_alpha_below_epsilon():
    """|alpha| < ε → 'neutral' (zone exclue agrégation)."""
    # alpha = +0.5% < ε=1.0% → neutral
    assert classify_direction(+5.0, +0.5, epsilon_neutral_pct=1.0) == "neutral"
    # alpha = -0.5% < ε=1.0% → neutral
    assert classify_direction(-5.0, -0.5, epsilon_neutral_pct=1.0) == "neutral"


def test_c1_classify_correct_when_signs_match():
    assert classify_direction(+5.0, +3.0) == "correct"
    assert classify_direction(-5.0, -3.0) == "correct"


def test_c1_classify_incorrect_when_signs_opposite():
    assert classify_direction(+5.0, -3.0) == "incorrect"
    assert classify_direction(-5.0, +3.0) == "incorrect"


def test_c1_classify_returns_none_on_invalid():
    assert classify_direction(None, 5.0) is None
    assert classify_direction(5.0, None) is None
    assert classify_direction(float("nan"), 5.0) is None
    assert classify_direction(5.0, float("inf")) is None


def test_c1_classify_epsilon_configurable():
    """ε ajustable par classe d'actif (defensible si justifié, doc obligatoire)."""
    # ε=2.0% → +1.5% reste neutral
    assert classify_direction(+5.0, +1.5, epsilon_neutral_pct=2.0) == "neutral"
    # ε=0.5% → +1.5% devient correct
    assert classify_direction(+5.0, +1.5, epsilon_neutral_pct=0.5) == "correct"


def test_c1_classify_no_bet_when_your_delta_below_epsilon():
    """|your_delta| < ε_delta → 'no_bet' (pendant symétrique de §6.8).

    Cas : your_target ≈ consensus, ta vue ne diverge pas de la foule.
    Verdict 'no_bet' (exclu agrégation) → pas scoré, pas une fausse 'correct'.

    Verrouille le trou de classify : sans ce seuil, une pose +0.1% delta
    vs alpha +5% donnerait 'correct' sur signe fragile, ET -0.1% delta vs
    alpha +5% donnerait 'incorrect' — mêmes alpha, verdicts opposés sur
    une 'pas de vue' identique.
    """
    # your_delta ±0.5% < ε_delta=1.0 → no_bet, indépendant de l'alpha
    assert classify_direction(+0.5, +5.0, epsilon_delta_pct=1.0) == "no_bet"
    assert classify_direction(-0.5, +5.0, epsilon_delta_pct=1.0) == "no_bet"
    assert classify_direction(+0.5, -5.0, epsilon_delta_pct=1.0) == "no_bet"
    # Even with neutral alpha, no_bet wins
    assert classify_direction(+0.5, +0.5, epsilon_delta_pct=1.0) == "no_bet"


def test_c1_classify_no_bet_priority_over_neutral():
    """no_bet > neutral > correct/incorrect dans l'ordre de priorité.

    Une pose sans pari ne devient pas correcte par chance, quel que soit
    l'alpha réalisé.
    """
    # |your_delta|=0.5 < ε_delta=1.0 → no_bet, même si |alpha|=0.5 aussi neutre
    assert classify_direction(+0.5, +0.5) == "no_bet"
    # |your_delta|=2.0 ≥ ε_delta → on évalue alpha. |alpha|=0.5 < ε_neutre → neutral
    assert classify_direction(+2.0, +0.5) == "neutral"
    # |your_delta|=2.0 ET |alpha|=2.0 → on classify le signe
    assert classify_direction(+2.0, +2.0) == "correct"


def test_c1_classify_epsilon_delta_configurable():
    """ε_delta ajustable, défaut 1.0 (symétrique à ε_neutre)."""
    # ε_delta=0.1 (très tolérant) → +0.5 devient un bet à scorer
    assert classify_direction(+0.5, +5.0, epsilon_delta_pct=0.1) == "correct"
    # ε_delta=5.0 (très strict) → +0.5 reste no_bet
    assert classify_direction(+0.5, +5.0, epsilon_delta_pct=5.0) == "no_bet"


def test_c1_classify_sk_and_ccj_pass_bet_threshold():
    """SK +72% et CCJ +16% : both passent largement ε_delta=1.0 — vrais paris."""
    # SK scenario : your_delta ≈ +72%, alpha hypothétique +20% → correct
    assert classify_direction(+72.2, +20.0) == "correct"
    # CCJ scenario : your_delta ≈ +16%, alpha hypothétique +10% → correct
    assert classify_direction(+16.0, +10.0) == "correct"
    # Negatif scenario : your_delta = -10% (bear), alpha = +5% (action a battu PT) → incorrect
    assert classify_direction(-10.0, +5.0) == "incorrect"


# ============================================================
# Scenarios end-to-end : SK Hynix + CCJ (backfill prévu §7 SPEC)
# ============================================================


def test_scenario_sk_hynix_blended_consensus_pt():
    """SK Hynix backfill scenario : consensus blended (moyenne ~2.3M KRW)
    NON bull-broker (~3.8M).

    asof_price_native = 2_077_000 KRW (cur à pose 10/06)
    pt_native_asof = 2_300_000 KRW (consensus moyen blended, décision Olivier
                                    pour éviter benchmark contre les optimistes)
    your_target_full = 3_800_000 KRW (ta full posée bull HBM gen5)

    your_delta_pct = (3.8M - 2.3M) / 2.077M × 100 = +72.2%
    Tu paries que SK bat le consensus moyen de +72%.
    """
    consensus_blended = {
        "pt": 2_300_000.0,
        "median": 2_300_000.0,
        "currency": "KRW",
        "asof": date(2026, 6, 10),
    }
    pr = convert_consensus_pt_to_native(consensus_blended, "KRW", 1.0)
    assert pr["fx_at_asof_used"] == 1.0  # no-op KRW→KRW

    your_delta = compute_your_delta_native_pct(
        your_target_native=3_800_000.0, pt_native_asof=pr["pt_native"], asof_price_native=2_077_000.0,
    )
    assert your_delta == pytest.approx((3_800_000 - 2_300_000) / 2_077_000 * 100)
    assert your_delta > 70.0  # bull thesis fort


def test_scenario_ccj_consensus_with_usd_no_fx_conversion():
    """CCJ : consensus USD + ticker USD → fx no-op même si consensus_ref absent
    du portfolio_rules.yaml (swap-out). Le PT vient du scorecard markdown.

    asof_price_native = 105.44 USD
    pt_native_asof = 138.0 USD (consensus médian de la table d'évidence)
    your_target_full = 155.0 USD
    """
    consensus = {"pt": 138.0, "median": 138.0, "currency": "USD", "asof": date(2026, 6, 10)}
    pr = convert_consensus_pt_to_native(consensus, "USD", 1.0)
    assert pr["pt_native"] == 138.0
    your_delta = compute_your_delta_native_pct(155.0, pr["pt_native"], 105.44)
    assert your_delta == pytest.approx((155 - 138) / 105.44 * 100)
    assert your_delta > 15.0  # bull modéré vs consensus
