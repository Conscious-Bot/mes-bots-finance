"""#94 Phase 3 -- ScoringOrchestrator tests.

Tests control-flow (mock-based) :
1. FLAG OFF (default) : LLMUnavailableError propage, fallback jamais appele
2. FLAG ON : LLMUnavailableError catch -> route fallback, tag bascule
3. Primary success : fallback jamais appele, tag = primary
4. Primary None (watch / JSON fail) : pas de fallback (None != error), tag = primary
5. from_env() : lit RESILIENCE_FALLBACK_ENABLED depuis l'env
6. Compat #93 : sans fallback, LLMUnavailableError remonte VERBATIM
7. Defense : exceptions non-LLM remontent (pas catch-all)

Pas property-based : control-flow / state machine.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from intelligence.scorers import LLMScorer, RuleScorer, ScorerInput
from intelligence.scoring_orchestrator import ScoringOrchestrator, _flag_enabled_from_env
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


def _make_mock_scorer(methodology_version: str, return_value: Any = None) -> MagicMock:
    m = MagicMock()
    m.methodology_version = methodology_version
    m.score = MagicMock(return_value=return_value)
    return m


# ─── 1. FLAG OFF : LLMUnavailableError propagates ────────────────────────


def test_flag_off_propagates_llm_unavailable_error():
    """Sans flag (default), LLMUnavailableError remonte. Compat #93 A1/A2."""
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = LLMUnavailableError("credit_exhausted", "")
    fallback = _make_mock_scorer("rule_v1_fallback", {"direction": "bullish"})
    orch = ScoringOrchestrator(primary, fallback, fallback_enabled=False)
    with pytest.raises(LLMUnavailableError) as exc_info:
        orch.score(_mk_input())
    assert exc_info.value.reason == "credit_exhausted"
    fallback.score.assert_not_called()  # fallback JAMAIS active sans flag


def test_flag_off_no_fallback_still_propagates():
    """Pas de fallback du tout + flag off -> LLMUnavailableError remonte."""
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = LLMUnavailableError("rate_limited", "")
    orch = ScoringOrchestrator(primary, fallback=None, fallback_enabled=False)
    with pytest.raises(LLMUnavailableError):
        orch.score(_mk_input())


# ─── 2. FLAG ON : LLMUnavailableError routes to fallback ────────────────


def test_flag_on_routes_to_fallback_on_llm_unavailable():
    """Flag ON + LLMUnavailableError -> fallback appele, tag bascule."""
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = LLMUnavailableError("credit_exhausted", "")
    fallback_data = {"direction": "bullish", "probability": 0.62}
    fallback = _make_mock_scorer("rule_v1_fallback", fallback_data)
    orch = ScoringOrchestrator(primary, fallback, fallback_enabled=True)
    data, tag = orch.score(_mk_input())
    assert data == fallback_data
    assert tag == "rule_v1_fallback"
    fallback.score.assert_called_once()


def test_flag_on_but_no_fallback_still_propagates():
    """Flag ON mais fallback=None : LLMUnavailableError remonte quand meme."""
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = LLMUnavailableError("credit_exhausted", "")
    orch = ScoringOrchestrator(primary, fallback=None, fallback_enabled=True)
    with pytest.raises(LLMUnavailableError):
        orch.score(_mk_input())


# ─── 3. Primary success : fallback jamais appele ────────────────────────


def test_primary_success_returns_primary_tag():
    """Primary OK -> retourne (primary_data, 'v2'). Fallback pas touche."""
    primary_data = {"direction": "bearish", "probability": 0.71}
    primary = _make_mock_scorer("v2", primary_data)
    fallback = _make_mock_scorer("rule_v1_fallback")
    orch = ScoringOrchestrator(primary, fallback, fallback_enabled=True)
    data, tag = orch.score(_mk_input())
    assert data == primary_data
    assert tag == "v2"
    fallback.score.assert_not_called()


# ─── 4. Primary returns None (watch / JSON fail) -> no fallback ─────────


def test_primary_returns_none_no_fallback():
    """None = scoring abouti mais pas de prediction (watch / parse fail).
    Ce n'est PAS une exception, fallback ne doit pas s'activer."""
    primary = _make_mock_scorer("v2", None)
    fallback = _make_mock_scorer("rule_v1_fallback", {"direction": "bullish"})
    orch = ScoringOrchestrator(primary, fallback, fallback_enabled=True)
    data, tag = orch.score(_mk_input())
    assert data is None
    assert tag == "v2"
    fallback.score.assert_not_called()


# ─── 5. from_env() factory + env flag parsing ───────────────────────────


def test_from_env_with_flag_off_default(monkeypatch):
    monkeypatch.delenv("RESILIENCE_FALLBACK_ENABLED", raising=False)
    orch = ScoringOrchestrator.from_env()
    assert orch.fallback_enabled is False
    assert isinstance(orch.primary, LLMScorer)
    assert isinstance(orch.fallback, RuleScorer)


def test_from_env_with_flag_on_1(monkeypatch):
    monkeypatch.setenv("RESILIENCE_FALLBACK_ENABLED", "1")
    orch = ScoringOrchestrator.from_env()
    assert orch.fallback_enabled is True


def test_from_env_with_flag_on_true(monkeypatch):
    monkeypatch.setenv("RESILIENCE_FALLBACK_ENABLED", "true")
    orch = ScoringOrchestrator.from_env()
    assert orch.fallback_enabled is True


def test_from_env_with_flag_off_other_values(monkeypatch):
    """Defense vs typo : 'false', '0', '' -> flag off."""
    for val in ("0", "false", "no", "", "FALSE_typo"):
        monkeypatch.setenv("RESILIENCE_FALLBACK_ENABLED", val)
        assert _flag_enabled_from_env() is False, f"Unexpected on for {val!r}"


# ─── 6. Defense : non-LLM exceptions remontent ─────────────────────────


def test_non_llm_exception_propagates_even_with_flag_on():
    """TypeError / KeyError / etc remontent. Fallback NE doit PAS catch tout."""
    primary = _make_mock_scorer("v2")
    primary.score.side_effect = TypeError("schema drift")
    fallback = _make_mock_scorer("rule_v1_fallback")
    orch = ScoringOrchestrator(primary, fallback, fallback_enabled=True)
    with pytest.raises(TypeError):
        orch.score(_mk_input())
    fallback.score.assert_not_called()
