"""v2.c.1 tests : classify_net_delta pure function (ADR 010 Addendum v2.c).

Verrouille la classification acted_on_bias / resisted sur DELTA NET.
Cas-limites partiel/reversal geres par construction -- testes ici qu'ils
SONT bien geres sans code special.

Note : trigger d'ouverture (rule reco -> open_candidate) NON-CABLE dans
cette passe -- v2.c.5 differe. Ces tests verrouillent la fonction pure ;
la creation des events reste manuelle/test only en attendant le cablage
du trigger d'emission.
"""

from __future__ import annotations

from intelligence.bias_events import classify_net_delta

# ─── lock_in : discipline = hold (expected_delta=0), winner ────────────────


def test_lock_in_acted_user_a_trim_winner() -> None:
    """lock_in : user a trim 40 du 100 (actual_delta=-40), discipline hold
    (expected=0). delta_vs_discipline = -40 < 0 = acted_on_bias."""
    action, taken, avoided, actual = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[{"qty_delta": -40.0}],
        initial_qty=100.0,
    )
    assert action == "acted_on_bias"
    assert taken == 60.0
    assert avoided == 100.0
    assert actual == -40.0


def test_lock_in_resisted_user_a_hold() -> None:
    """lock_in : user tient (actual_delta=0), discipline hold (expected=0)
    = resisted (matche discipline)."""
    action, taken, avoided, actual = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[],
        initial_qty=100.0,
    )
    assert action == "resisted"
    assert taken == 100.0
    assert avoided == 100.0
    assert actual == 0.0


# ─── fomo_greed : discipline = trim/exit (expected_delta<0) ────────────────


def test_fomo_greed_acted_user_a_tenu_malgre_signal_exit() -> None:
    """fomo_greed : signal exit (discipline expected=-50), user tient
    (actual=0). delta_vs_discipline = 0 - (-50) = +50 > 0 = acted_on_bias
    (tenu au-dela du top)."""
    action, taken, avoided, actual = classify_net_delta(
        bias="fomo_greed",
        discipline_expected_delta=-50.0,
        position_events_in_window=[],
        initial_qty=100.0,
    )
    assert action == "acted_on_bias"
    assert taken == 100.0
    assert avoided == 50.0
    assert actual == 0.0


def test_fomo_greed_resisted_user_a_sorti_comme_discipline_dit() -> None:
    """fomo_greed : signal exit (discipline=-50), user a sorti -50
    (matche). delta_vs_discipline = 0 = resisted."""
    action, taken, avoided, actual = classify_net_delta(
        bias="fomo_greed",
        discipline_expected_delta=-50.0,
        position_events_in_window=[{"qty_delta": -50.0}],
        initial_qty=100.0,
    )
    assert action == "resisted"
    assert taken == 50.0
    assert avoided == 50.0


# ─── Cas-limites : partiel + reversal geres par construction (delta net) ──


def test_partial_magnitude_reflechi_dans_shares_delta() -> None:
    """ADR Addendum : 'l'action partielle = magnitude plus faible (pas un
    cas special)'. lock_in user trim seulement 15 (au lieu de 40 plein) :
    classification toujours acted_on_bias MAIS magnitude moindre (shares_taken
    plus proche de shares_avoided)."""
    action, taken, avoided, actual = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[{"qty_delta": -15.0}],
        initial_qty=100.0,
    )
    assert action == "acted_on_bias"
    assert taken == 85.0  # vs 60 si trim complet
    assert avoided == 100.0
    assert actual == -15.0
    # Magnitude du biais = abs(actual - expected) = 15 (vs 40 si plein)
    assert abs(actual - 0.0) == 15.0


def test_reversal_net_pas_cas_special() -> None:
    """ADR Addendum : 'action-puis-reversal = le net (pas un cas special)'.
    User vend -40 puis re-achete +40 le lendemain. Net delta = 0 = resisted
    (a finalement tenu malgre l'oscillation)."""
    action, taken, avoided, actual = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[
            {"qty_delta": -40.0, "occurred_at": "2026-05-15"},
            {"qty_delta": +40.0, "occurred_at": "2026-05-16"},
        ],
        initial_qty=100.0,
    )
    assert action == "resisted"  # malgre l'oscillation, finit a discipline
    assert taken == 100.0
    assert avoided == 100.0
    assert actual == 0.0


# ─── other : conservatif ───────────────────────────────────────────────────


def test_other_tie_donne_resisted() -> None:
    """bias='other' : si tie (actual == expected exactement) = resisted."""
    action, _, _, _ = classify_net_delta(
        bias="other",
        discipline_expected_delta=0.0,
        position_events_in_window=[],
        initial_qty=100.0,
    )
    assert action == "resisted"


def test_other_non_zero_donne_acted() -> None:
    """bias='other' : delta non-nul hors tolerance = acted (conservatif)."""
    action, _, _, _ = classify_net_delta(
        bias="other",
        discipline_expected_delta=0.0,
        position_events_in_window=[{"qty_delta": -10.0}],
        initial_qty=100.0,
    )
    assert action == "acted_on_bias"


# ─── Seuil noise (user 01/06) : piege hold + 1 trade bruit ─────────────────


def test_lock_in_hold_avec_noise_trade_reste_resisted() -> None:
    """Piege classique : discipline=hold (expected=0), user fait 1 trade
    de bruit (-2 shares sur 100). |delta_vs_discipline|=2 < 5%*100=5
    -> tolerance NOISE -> resisted. Avant le fix : aurait flippe acted
    a tort. Aligne user spec 01/06."""
    action, taken, avoided, actual = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[{"qty_delta": -2.0}],
        initial_qty=100.0,
    )
    assert action == "resisted", "trade bruit -2 sur 100 doit etre resisted (dans tolerance 5%)"
    assert actual == -2.0  # la magnitude est preservee (-> delta_signed)
    assert taken == 98.0


def test_lock_in_au_seuil_exact_du_threshold_reste_resisted() -> None:
    """delta_vs_discipline exactement au seuil (5% = 5 shares sur 100)
    -> resisted (boundary inclusive). Le label = match-ecart-zone, pas
    cliff."""
    action, _, _, _ = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[{"qty_delta": -5.0}],
        initial_qty=100.0,
    )
    assert action == "resisted"


def test_lock_in_juste_au_dessus_du_seuil_devient_acted() -> None:
    """Juste au-dessus du seuil (5.1 sur 100) -> acted_on_bias. Pas de
    cliff abusif : 5.1 > 5.0 strict."""
    action, _, _, _ = classify_net_delta(
        bias="lock_in",
        discipline_expected_delta=0.0,
        position_events_in_window=[{"qty_delta": -5.1}],
        initial_qty=100.0,
    )
    assert action == "acted_on_bias"


def test_fomo_greed_rightsize_approxime_reste_resisted() -> None:
    """fomo_greed : discipline rightsize de -20 (e.g., trim 20 shares
    pour atteindre cap). User a trim -19 (approche cible, dans tolerance).
    delta_vs_discipline = -19 - (-20) = +1. |1| <= 5% * 100 = 5 -> resisted.
    Le label = match-cible-zone, magnitude (-19) part vers delta_signed."""
    action, taken, avoided, _ = classify_net_delta(
        bias="fomo_greed",
        discipline_expected_delta=-20.0,
        position_events_in_window=[{"qty_delta": -19.0}],
        initial_qty=100.0,
    )
    assert action == "resisted"
    assert taken == 81.0  # initial + actual = 100 + (-19)
    assert avoided == 80.0  # initial + expected = 100 + (-20)
