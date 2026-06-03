"""#94 Phase 1 -- Scorer Protocol + LLMScorer adapter (zero-behavior change).

Tests structurels (mock-based) qui garantissent :
- LLMScorer respecte le Scorer Protocol (structural typing implicite)
- LLMScorer.methodology_version == 'v2' (tag canonical, jamais default)
- LLMScorer.score() delegue VERBATIM a score_directional_probability avec
  signature alignee
- LLMUnavailableError remonte (NEVER swallowed) -- prerequis #93 + #94
- Exceptions backend retournent None (skip silencieux, log warning OK)
- ScorerInput est frozen + slots (defensive immutability)

Pas property-based : control-flow + adapter wiring. Le math est dans
score_directional_probability (deja teste ailleurs).
"""

from __future__ import annotations

from typing import get_type_hints
from unittest.mock import patch

import pytest

from intelligence.scorers import LLMScorer, Scorer, ScorerInput

# ─── ScorerInput contract ─────────────────────────────────────────────────


def test_scorer_input_is_frozen():
    """ScorerInput est dataclass frozen -- mutation interdite (defense vs
    mutation accidentelle apres construction)."""
    from dataclasses import FrozenInstanceError

    inp = ScorerInput(title="t", ticker="NVDA", horizon_days=28)
    with pytest.raises(FrozenInstanceError):
        inp.ticker = "MSFT"  # type: ignore[misc]


def test_scorer_input_required_fields():
    """title + ticker + horizon_days sont required. Reste optionnel."""
    inp = ScorerInput(title="x", ticker="NVDA", horizon_days=28)
    assert inp.title == "x"
    assert inp.ticker == "NVDA"
    assert inp.horizon_days == 28
    assert inp.summary is None
    assert inp.content is None
    assert inp.entities is None
    assert inp.source_name is None


# ─── LLMScorer attributs ──────────────────────────────────────────────────


def test_llm_scorer_methodology_version_is_v2():
    """ADR 014 hazard B : methodology_version est explicite, jamais default.
    LLMScorer porte 'v2' (canonical post-J-day)."""
    assert LLMScorer.methodology_version == "v2"
    # Instance attribute aussi
    assert LLMScorer().methodology_version == "v2"


def test_llm_scorer_structurally_implements_scorer_protocol():
    """LLMScorer doit avoir methodology_version + score(). Protocol matching
    structurel via attributs + methode."""
    s = LLMScorer()
    # Structural : a-t-il les attributs attendus
    assert hasattr(s, "methodology_version")
    assert hasattr(s, "score")
    assert callable(s.score)
    # Type hints attendus (defense vs drift de signature)
    hints = get_type_hints(LLMScorer.score)
    assert "inp" in hints
    assert hints["inp"] is ScorerInput


# ─── LLMScorer.score() delegation ─────────────────────────────────────────


def test_llm_scorer_delegates_to_signal_scorer_v2():
    """LLMScorer.score() doit appeler score_directional_probability avec les
    memes kwargs verbatim. Garantit zero-behavior change vs path direct."""
    inp = ScorerInput(
        title="NVDA 8-K Q1 beat",
        ticker="NVDA",
        horizon_days=28,
        summary="Beat top + bottom",
        content="Q1 revenue 35B vs 32B est",
        entities=["NVDA"],
        source_name="EDGAR_8K",
    )
    expected_return = {
        "version": "v2.0",
        "ticker": "NVDA",
        "horizon_days": 28,
        "base_rate": 0.55,
        "evidence_strength": "strong",
        "evidence_summary": "Q1 beat material",
        "anti_anchoring_reason": "Specific quantifiable beat justifies +20pts.",
        "probability": 0.75,
        "direction": "bullish",
        "reasoning": "Earnings beat with magnitude.",
    }
    with patch(
        "intelligence.signal_scorer_v2.score_directional_probability",
        return_value=expected_return,
    ) as mock_score:
        out = LLMScorer().score(inp)

    mock_score.assert_called_once_with(
        title="NVDA 8-K Q1 beat",
        summary="Beat top + bottom",
        ticker="NVDA",
        horizon_days=28,
        content="Q1 revenue 35B vs 32B est",
        entities=["NVDA"],
        source_name="EDGAR_8K",
    )
    assert out == expected_return


def test_llm_scorer_returns_none_when_backend_returns_none():
    """JSON parse fail, watch direction, etc -> backend returns None.
    LLMScorer doit propager None tel quel (caller skip le signal)."""
    inp = ScorerInput(title="x", ticker="X", horizon_days=28)
    with patch(
        "intelligence.signal_scorer_v2.score_directional_probability",
        return_value=None,
    ):
        out = LLMScorer().score(inp)
    assert out is None


# ─── LLMUnavailableError propagation (NEVER swallow) ─────────────────────


def test_llm_scorer_propagates_llm_unavailable_error():
    """Si shared.llm raise LLMUnavailableError au backend, LLMScorer doit
    laisser remonter SANS swallow. C'est le contrat #93 chokepoint : le
    caller (orchestrator phase 3) attrape pour switch RuleScorer, OU
    consumer marque pending_llm.

    JAMAIS de drop silencieux ici (lecon tennis-bot, spec user 03/06)."""
    from shared.llm import LLMUnavailableError

    inp = ScorerInput(title="x", ticker="X", horizon_days=28)
    err = LLMUnavailableError("credit_exhausted", upstream_msg="balance low")
    with patch(
        "intelligence.signal_scorer_v2.score_directional_probability",
        side_effect=err,
    ), pytest.raises(LLMUnavailableError) as exc_info:
        LLMScorer().score(inp)
    assert exc_info.value.reason == "credit_exhausted"


# ─── Defensive : adapter ne masque pas les exceptions structurelles ─────


def test_llm_scorer_does_not_catch_unrelated_exceptions():
    """Les exceptions non-LLM (KeyError, TypeError, etc) du backend doivent
    remonter aussi -- l'adapter ne sert PAS de catch-all. Le backend fait
    deja son propre filtering (JSONDecodeError + generic Exception -> None).
    Mais si le backend raise au pre-call (TypeError signature drift), c'est
    un bug a surfacer, pas un None silencieux."""
    inp = ScorerInput(title="x", ticker="X", horizon_days=28)
    with patch(
        "intelligence.signal_scorer_v2.score_directional_probability",
        side_effect=TypeError("unexpected signature"),
    ), pytest.raises(TypeError):
        LLMScorer().score(inp)


# ─── Structural conformance au Protocol (runtime check optionnel) ────────


def test_llm_scorer_satisfies_scorer_protocol_structurally():
    """Conformance Protocol = duck typing. isinstance check optionnel via
    @runtime_checkable (pas active ici, mais on verifie manuellement les
    attributs attendus)."""
    # Le Protocol Scorer demande :
    #   - methodology_version: str
    #   - score(self, inp: ScorerInput) -> dict | None
    s: Scorer = LLMScorer()  # type-check pass via structural typing
    assert isinstance(s.methodology_version, str)
    assert callable(s.score)
