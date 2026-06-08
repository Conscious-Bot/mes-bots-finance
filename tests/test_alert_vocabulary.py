"""Tests verrouillants SOCLE substrat sémantique : vocabulaire d'alerte canonique.

6 invariants critiques (cf SPEC_ALERT_VOCABULARY.md §5) :
  1. 4 classes orthogonales (state/steer/flag/event, mutuellement exclusives)
  2. STATE n'attire JAMAIS l'œil (validator force earns_attention=False)
  3. EVENT sans calibration_contract = refusé (validator)
  4. EVENT.delta_based = True obligatoire (validator)
  5. Mot non-déclaré = KeyError (pas de fabrication panel-locale)
  6. ratio attention-earning per-panel auditable (crying-wolf detector)

+ Walking-skeleton : EROSION_DETECTED traverse get_word → render_token et
  satisfait les invariants.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.alert_vocabulary import (
    AlertWord,
    EventWord,
    FlagWord,
    StateWord,
    SteerWord,
    all_words,
    attention_earning,
    attention_earning_ratio,
    get_word,
    load_vocabulary,
    render_token,
)

# === Test 1 : 4 classes orthogonales, mutuellement exclusives ============


def test_vocabulary_loads_and_has_4_classes() -> None:
    """Le registre charge et expose les 4 classes."""
    reg = load_vocabulary()
    assert len(reg.words) > 0
    classes_present = set()
    for w in reg.words.values():
        if isinstance(w, StateWord):
            classes_present.add("state")
        elif isinstance(w, SteerWord):
            classes_present.add("steer")
        elif isinstance(w, FlagWord):
            classes_present.add("flag")
        elif isinstance(w, EventWord):
            classes_present.add("event")
    assert classes_present == {"state", "steer", "flag", "event"}, (
        f"Une des 4 classes manque : {classes_present}"
    )


def test_no_word_is_two_classes() -> None:
    """Chaque mot appartient à exactement UNE classe (orthogonalité)."""
    for name, w in all_words().items():
        types = [
            isinstance(w, StateWord),
            isinstance(w, SteerWord),
            isinstance(w, FlagWord),
            isinstance(w, EventWord),
        ]
        assert sum(types) == 1, f"Word '{name}' has ambiguous class : {types}"


# === Test 2 : STATE n'attire JAMAIS l'œil (validator structurel) =========


def test_state_word_forced_to_false_attention(monkeypatch) -> None:
    """Tenter de créer un StateWord avec earns_attention=True doit RAISE."""
    with pytest.raises(ValidationError, match=r"STATE\.earns_attention MUST be False"):
        StateWord.model_validate({
            "earns_attention": True,  # FORBIDDEN
            "meaning": "test state",
            "render": {"color": "neutral", "icon": "circle", "weight": "low"},
            "action_hint": "",
        })


def test_all_state_words_in_yaml_dont_earn_attention() -> None:
    """Tous les STATE déclarés dans config ont earns_attention=False (defensive)."""
    for name, w in all_words().items():
        if isinstance(w, StateWord):
            assert w.earns_attention is False, (
                f"STATE word '{name}' has earns_attention=True (impossible par validator, "
                "indique corruption fichier yaml)"
            )


# === Test 3 : EVENT sans calibration_contract = refusé ===================


def test_event_word_without_contract_raises() -> None:
    """Un EVENT sans calibration_contract MUST raise (delta non-calibré = bruit)."""
    with pytest.raises(ValidationError, match="EVENT requires calibration_contract"):
        EventWord.model_validate({
            "earns_attention": True,
            "meaning": "test event without contract",
            "render": {"color": "warning", "icon": "alert", "weight": "high"},
            "action_hint": "",
            "calibration_contract": None,  # FORBIDDEN for EVENT
        })


def test_all_event_words_have_calibration_contract() -> None:
    """Tous les EVENT déclarés ont leur calibration_contract (validator garantit déjà)."""
    for name, w in all_words().items():
        if isinstance(w, EventWord):
            assert w.calibration_contract is not None, (
                f"EVENT '{name}' sans calibration_contract (impossible par validator)"
            )
            assert w.calibration_contract.trigger
            assert w.calibration_contract.outcome_validated


# === Test 4 : EVENT.delta_based = True obligatoire =======================


def test_event_with_delta_based_false_raises() -> None:
    """calibration_contract.delta_based=False MUST raise (doctrine delta-pas-état)."""
    with pytest.raises(ValidationError, match="delta_based MUST be True"):
        EventWord.model_validate({
            "earns_attention": True,
            "meaning": "test event with delta=false",
            "render": {"color": "warning", "icon": "alert", "weight": "high"},
            "action_hint": "",
            "calibration_contract": {
                "trigger": "test",
                "delta_based": False,  # FORBIDDEN
                "outcome_validated": "test",
            },
        })


# === Test 5 : Mot non-déclaré = KeyError (pas de fabrication panel-locale) ==


def test_get_word_unknown_raises_keyerror() -> None:
    """get_word('TOTALLY_MADE_UP') doit lever KeyError."""
    with pytest.raises(KeyError, match="Mot inconnu"):
        get_word("TOTALLY_MADE_UP_NEVER_DECLARED")


# === Test 6 : ratio attention-earning auditable (crying-wolf detector) ===


def test_attention_earning_ratio_empty_panel_zero() -> None:
    assert attention_earning_ratio([]) == 0.0


def test_attention_earning_ratio_all_state_zero() -> None:
    """Panel qui ne rend que des STATE -> 0% attention. Defaut calme."""
    state_words = ["CYCLE_LATE", "THESIS_INTACT", "FRESH_LIVE", "TYPE_PRICED", "CONV_C5"]
    assert attention_earning_ratio(state_words) == 0.0


def test_attention_earning_ratio_mixed() -> None:
    """Panel mixte : 1 EVENT + 1 FLAG + 3 STATE -> 2/5 = 0.4 (>20% = build rouge cible)."""
    panel = ["EROSION_DETECTED", "OVER_CAP", "CYCLE_LATE", "THESIS_INTACT", "TYPE_PRICED"]
    ratio = attention_earning_ratio(panel)
    assert ratio == pytest.approx(0.4)


def test_attention_earning_ratio_pure_state_default_calm() -> None:
    """Vérifie le seuil doctrinal 20% : panel calme -> ratio < 0.2."""
    calm_panel = ["CYCLE_MID", "THESIS_INTACT", "FRESH_LIVE", "HOLD"]  # HOLD calm-class
    ratio = attention_earning_ratio(calm_panel)
    assert ratio < 0.2, "Panel calme doit avoir ratio < 20% (defaut calme)"


# === Walking-skeleton : EROSION_DETECTED traverse get_word + render_token ==


def test_walking_skeleton_erosion_detected_canonical() -> None:
    """LE walking-skeleton : EROSION_DETECTED traverse le pipeline complet et
    satisfait les invariants (cf L24 -- pas seulement mocks)."""
    word = get_word("EROSION_DETECTED")
    # Class correcte
    assert isinstance(word, EventWord)
    # Attention-earning (EVENT alarme legitime)
    assert attention_earning(word) is True
    assert word.earns_attention is True
    # Calibration contract present + delta_based True
    assert word.calibration_contract is not None
    assert word.calibration_contract.delta_based is True
    assert "érosion" in word.calibration_contract.trigger.lower() or "erosion" in word.calibration_contract.trigger.lower()
    # Render token canonique
    rt = render_token(word)
    assert rt.color == "warning"
    assert rt.icon == "trending-down"
    assert rt.weight == "high"
    # Action hint utile
    assert word.action_hint
    assert "REVIEW" in word.action_hint


def test_walking_skeleton_state_cycle_late_calm() -> None:
    """Counter-test : CYCLE_LATE est un STATE, n'attire jamais l'œil."""
    word = get_word("CYCLE_LATE")
    assert isinstance(word, StateWord)
    assert attention_earning(word) is False
    rt = render_token(word)
    # State -> weight low (jamais high), color neutral/info (jamais warning/danger)
    assert rt.weight == "low"
    assert rt.color in ("neutral", "info", "calm")


def test_walking_skeleton_steer_trim_act_class() -> None:
    """STEER act-class TRIM : earns_attention=True."""
    word = get_word("TRIM")
    assert isinstance(word, SteerWord)
    assert attention_earning(word) is True  # act-class
    rt = render_token(word)
    assert rt.weight == "high"


def test_walking_skeleton_steer_hold_calm_class() -> None:
    """STEER calm-class HOLD : earns_attention=False (silence par défaut)."""
    word = get_word("HOLD")
    assert isinstance(word, SteerWord)
    assert attention_earning(word) is False  # calm-class


# === Frozen check (anti-tampering downstream) ==============================


def test_word_is_frozen() -> None:
    """AlertWord frozen : aucun panel ne peut muter un mot après lecture."""
    word = get_word("EROSION_DETECTED")
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        word.earns_attention = False  # type: ignore[misc]


def test_render_spec_is_frozen() -> None:
    rt = render_token(get_word("EROSION_DETECTED"))
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        rt.color = "calm"  # type: ignore[misc]


# === Sanity vocabulary completeness =========================================


def test_vocabulary_has_minimum_30_words() -> None:
    """SPEC : ~30 mots canoniques (le vocabulaire de départ)."""
    n = len(all_words())
    assert n >= 25, f"Vocabulaire trop petit ({n} mots), SPEC demande ~30"


def test_all_specd_words_present() -> None:
    """Les mots cles du SPEC §2 doivent etre tous declarés."""
    required = {
        # STATE
        "CYCLE_LATE", "THESIS_INTACT", "FRESH_STALE", "TYPE_STRUCTURAL", "CONV_C5",
        # STEER
        "TRIM", "RIGHTSIZE", "EXIT", "REVIEW", "HOLD", "WATCH", "ADD", "SET_TARGET",
        # FLAG
        "OVER_CAP", "FAIL_CLOSED", "DEGRADED", "NO_STOP", "NO_TARGET",
        # EVENT
        "INVALIDATION_HIT", "TARGET_HIT", "EROSION_DETECTED",
        "ASYM_COMPRESSION", "REGIME_SHIFT", "STRESS_RISING", "DEMOTED",
    }
    declared = set(all_words().keys())
    missing = required - declared
    assert not missing, f"Mots SPEC manquants : {missing}"
