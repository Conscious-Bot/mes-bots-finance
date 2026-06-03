"""#96 -- Champion-Challenger Shadow Scoring tests.

Tests control-flow + state machine (mock-based) :
1. FLAG OFF (default) : shadow ne tire pas, primary inchange
2. FLAG ON : les deux tirent, ShadowPairedResult complet
3. Primary LLMUnavailableError : remonte, shadow PAS active (pair sans
   sens si LLM down -- caller doit basculer vers #94 fallback orchestrator)
4. Primary returns None (watch / JSON fail) : shadow tire quand meme
   (None != error)
5. Shadow exception : avalee + log warning, primary preserved
6. from_env() : parsing flag RESILIENCE_SHADOW_ENABLED
7. Guard : shadow doit avoir methodology_version rule-family ('rule_v1_shadow'
   ou 'rule_v1_fallback'), sinon ValueError
8. Helpers should_register_prediction + is_paired

Pas property-based : control-flow / orchestration state machine.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from intelligence.scorers import LLMScorer, RuleScorer, ScorerInput
from intelligence.shadow_scoring import (
    PairedShadowOrchestrator,
    ShadowPairedResult,
    _flag_enabled_from_env,
    is_paired,
    should_register_prediction,
)
from shared.llm import LLMUnavailableError


def _mk_input() -> ScorerInput:
    return ScorerInput(
        title="NVDA 8-K",
        ticker="NVDA",
        horizon_days=28,
        signal_score=8,
        signal_type="earnings_beat",
        impact_magnitude=0.5,
        sentiment="bullish",
    )


def _make_mock_scorer(methodology_version: str, return_value=None):
    m = MagicMock()
    m.methodology_version = methodology_version
    m.score = MagicMock(return_value=return_value)
    return m


# ─── 1. FLAG OFF : shadow ne tire pas ────────────────────────────────────


def test_flag_off_shadow_not_called():
    """Default state : flag off -> shadow.score() jamais appele."""
    primary_data = {"direction": "bullish", "probability": 0.72}
    primary = _make_mock_scorer("v2", primary_data)
    shadow = _make_mock_scorer("rule_v1_shadow", {"direction": "bullish"})
    orch = PairedShadowOrchestrator(primary, shadow, enabled=False)
    result = orch.score(_mk_input())
    assert result.primary_data == primary_data
    assert result.primary_tag == "v2"
    assert result.shadow_data is None
    assert result.shadow_tag is None
    shadow.score.assert_not_called()


def test_flag_off_propagates_llm_unavailable_error():
    """FLAG OFF + LLM down : LLMUnavailableError remonte (compat #93)."""
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = LLMUnavailableError("credit_exhausted", "")
    shadow = _make_mock_scorer("rule_v1_shadow", {"direction": "bullish"})
    orch = PairedShadowOrchestrator(primary, shadow, enabled=False)
    with pytest.raises(LLMUnavailableError):
        orch.score(_mk_input())
    shadow.score.assert_not_called()


# ─── 2. FLAG ON : les deux tirent en pair ────────────────────────────────


def test_flag_on_both_run_and_returned():
    """FLAG ON : primary + shadow tous deux appeles, resultats apparies."""
    primary_data = {"direction": "bullish", "probability": 0.72, "version": "v2.0"}
    shadow_data = {"direction": "bullish", "probability": 0.62, "version": "rule_v1"}
    primary = _make_mock_scorer("v2", primary_data)
    shadow = _make_mock_scorer("rule_v1_shadow", shadow_data)
    orch = PairedShadowOrchestrator(primary, shadow, enabled=True)
    result = orch.score(_mk_input())
    assert result.primary_data == primary_data
    assert result.primary_tag == "v2"
    assert result.shadow_data == shadow_data
    assert result.shadow_tag == "rule_v1_shadow"
    primary.score.assert_called_once()
    shadow.score.assert_called_once()


def test_flag_on_both_called_with_same_input():
    """Variante b independent : meme ScorerInput passe aux deux. Pas de fork."""
    primary = _make_mock_scorer("v2", {"direction": "bullish"})
    shadow = _make_mock_scorer("rule_v1_shadow", {"direction": "watch"})
    orch = PairedShadowOrchestrator(primary, shadow, enabled=True)
    inp = _mk_input()
    orch.score(inp)
    primary.score.assert_called_once_with(inp)
    shadow.score.assert_called_once_with(inp)


# ─── 3. Primary LLMUnavailableError : shadow NOT activated ──────────────


def test_flag_on_llm_unavailable_propagates_shadow_not_called():
    """Si primary raise LLMUnavailableError ET flag ON, shadow ne tire PAS.

    Le pair n'a pas de sens si LLM down (rationale : on mesure LLM vs Rule ;
    si LLM ne tire pas, il n'y a rien a comparer). Le caller doit basculer
    sur #94 ScoringOrchestrator (fallback) pour resilience.
    """
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = LLMUnavailableError("credit_exhausted", "balance")
    shadow = _make_mock_scorer("rule_v1_shadow", {"direction": "bullish"})
    orch = PairedShadowOrchestrator(primary, shadow, enabled=True)
    with pytest.raises(LLMUnavailableError) as exc:
        orch.score(_mk_input())
    assert exc.value.reason == "credit_exhausted"
    shadow.score.assert_not_called()


# ─── 4. Primary None (watch / JSON fail) : shadow still runs ────────────


def test_primary_returns_none_shadow_still_runs():
    """Primary None = scoring abouti mais pas de pred (watch). Shadow tire
    quand meme : c'est un data point pour la comparaison (Rule aurait fait
    un call la ou LLM a abandonne -- informatif)."""
    primary = _make_mock_scorer("v2", None)
    shadow_data = {"direction": "bullish", "probability": 0.65}
    shadow = _make_mock_scorer("rule_v1_shadow", shadow_data)
    orch = PairedShadowOrchestrator(primary, shadow, enabled=True)
    result = orch.score(_mk_input())
    assert result.primary_data is None
    assert result.primary_tag == "v2"
    assert result.shadow_data == shadow_data
    assert result.shadow_tag == "rule_v1_shadow"
    shadow.score.assert_called_once()


# ─── 5. Shadow exception : avalee, primary preserved ───────────────────


def test_shadow_exception_does_not_affect_primary():
    """Ban absolu : shadow ne doit JAMAIS affecter primary. Si shadow crash,
    on retourne primary normal + shadow=None + log warning."""
    primary_data = {"direction": "bullish", "probability": 0.72}
    primary = _make_mock_scorer("v2", primary_data)
    shadow = _make_mock_scorer("rule_v1_shadow")
    shadow.score.side_effect = RuntimeError("DB connection failed")
    orch = PairedShadowOrchestrator(primary, shadow, enabled=True)
    # Pas de raise -- on continue le primary path
    result = orch.score(_mk_input())
    assert result.primary_data == primary_data
    assert result.primary_tag == "v2"
    assert result.shadow_data is None
    assert result.shadow_tag is None


# ─── 6. from_env() factory ───────────────────────────────────────────────


def test_from_env_default_flag_off(monkeypatch):
    monkeypatch.delenv("RESILIENCE_SHADOW_ENABLED", raising=False)
    orch = PairedShadowOrchestrator.from_env()
    assert orch.enabled is False
    assert isinstance(orch.primary, LLMScorer)
    assert isinstance(orch.shadow, RuleScorer)
    assert orch.shadow.methodology_version == "rule_v1_shadow"


def test_from_env_flag_on(monkeypatch):
    monkeypatch.setenv("RESILIENCE_SHADOW_ENABLED", "1")
    orch = PairedShadowOrchestrator.from_env()
    assert orch.enabled is True


def test_flag_parser_recognizes_truthy_values(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("RESILIENCE_SHADOW_ENABLED", val)
        assert _flag_enabled_from_env() is True


def test_flag_parser_rejects_typos_and_off_values(monkeypatch):
    """Defense vs typo : '0', 'false', '' -> flag off."""
    for val in ("0", "false", "no", "", "FALSE_typo", "on_typo"):
        monkeypatch.setenv("RESILIENCE_SHADOW_ENABLED", val)
        assert _flag_enabled_from_env() is False, f"Unexpected on for {val!r}"


# ─── 7. Init guard : shadow must be rule-family ─────────────────────────


def test_init_rejects_non_rule_shadow_tag():
    """ADR 014 § Substance tier : shadow doit etre rule_v1_*. Si on passe
    un LLMScorer tagge 'v2' comme shadow, init rejette (sinon shadow tag
    contaminerait canonical filters)."""
    primary = LLMScorer()
    fake_shadow = MagicMock()
    fake_shadow.methodology_version = "v2"
    with pytest.raises(ValueError, match="rule_v1_shadow"):
        PairedShadowOrchestrator(primary, fake_shadow, enabled=True)


def test_init_rejects_unknown_tag():
    primary = LLMScorer()
    fake_shadow = MagicMock()
    fake_shadow.methodology_version = "rule_v2_shadow"  # famille non encore declaree
    with pytest.raises(ValueError):
        PairedShadowOrchestrator(primary, fake_shadow, enabled=True)


def test_init_accepts_rule_v1_fallback_tag():
    """Variante : un fallback peut servir de shadow pour mesurer un cycle
    LLM healthy avec on-the-side fallback-tagged predictions (analyse
    croisee)."""
    primary = LLMScorer()
    shadow = RuleScorer(methodology_version="rule_v1_fallback")
    orch = PairedShadowOrchestrator(primary, shadow, enabled=True)
    assert orch.shadow.methodology_version == "rule_v1_fallback"


# ─── 8. Helpers should_register_prediction + is_paired ──────────────────


def test_should_register_prediction_true_for_bullish():
    assert should_register_prediction({"direction": "bullish"}) is True


def test_should_register_prediction_true_for_bearish():
    assert should_register_prediction({"direction": "bearish"}) is True


def test_should_register_prediction_false_for_watch():
    assert should_register_prediction({"direction": "watch"}) is False


def test_should_register_prediction_false_for_none():
    assert should_register_prediction(None) is False


def test_should_register_prediction_false_for_missing_direction():
    """data sans 'direction' -> False (defense vs schema drift)."""
    assert should_register_prediction({"probability": 0.7}) is False


def test_is_paired_true_when_both_registrable():
    result = ShadowPairedResult(
        primary_data={"direction": "bullish"},
        primary_tag="v2",
        shadow_data={"direction": "bearish"},  # peut diverger directionnellement
        shadow_tag="rule_v1_shadow",
    )
    assert is_paired(result) is True


def test_is_paired_false_when_primary_watch():
    result = ShadowPairedResult(
        primary_data={"direction": "watch"},
        primary_tag="v2",
        shadow_data={"direction": "bullish"},
        shadow_tag="rule_v1_shadow",
    )
    assert is_paired(result) is False


def test_is_paired_false_when_shadow_none():
    """Flag off case : shadow_data None -> pas paire."""
    result = ShadowPairedResult(
        primary_data={"direction": "bullish"},
        primary_tag="v2",
        shadow_data=None,
        shadow_tag=None,
    )
    assert is_paired(result) is False
