"""Tests for bias_tagger.auto_tag_biases with mocked LLM.

Covers: response shape handling (list, dict variants), tag filtering,
exception fallback, prompt context inclusion.
"""

from unittest.mock import patch

from intelligence.bias_tagger import BIASES, auto_tag_biases

# ─────────────────────────────────────────────────────────
# Response shape handling
# ─────────────────────────────────────────────────────────


def test_list_response_returns_valid_tags():
    """LLM returns a list of valid bias names."""
    decision = {"ticker": "NVDA", "decision_type": "entry", "reasoning": "All-time high momentum"}
    with patch("shared.llm.call_json", return_value=["fomo", "narrative_capture"]):
        tags = auto_tag_biases(decision)
    assert tags == ["fomo", "narrative_capture"]


def test_dict_response_with_tags_key():
    """LLM returns a dict wrapping the list under 'tags' key."""
    decision = {"ticker": "BTC", "decision_type": "entry", "reasoning": "ATH parabolic"}
    with patch("shared.llm.call_json", return_value={"tags": ["fomo", "anchoring"]}):
        tags = auto_tag_biases(decision)
    assert set(tags) == {"fomo", "anchoring"}


def test_dict_response_with_biases_key():
    """LLM returns a dict wrapping under 'biases' key (alt format)."""
    decision = {"ticker": "TSLA", "decision_type": "scale_in"}
    with patch("shared.llm.call_json", return_value={"biases": ["confirmation_bias"]}):
        tags = auto_tag_biases(decision)
    assert tags == ["confirmation_bias"]


def test_empty_list_returns_empty():
    """LLM correctly identifies no clear bias."""
    decision = {"ticker": "AAPL", "decision_type": "entry"}
    with patch("shared.llm.call_json", return_value=[]):
        tags = auto_tag_biases(decision)
    assert tags == []


# ─────────────────────────────────────────────────────────
# Tag validation / filtering
# ─────────────────────────────────────────────────────────


def test_invalid_tags_filtered_out():
    """LLM hallucinates a non-existing bias name - must be filtered."""
    decision = {"ticker": "NVDA", "decision_type": "entry"}
    with patch("shared.llm.call_json", return_value=["fomo", "hallucinated_bias", "anchoring"]):
        tags = auto_tag_biases(decision)
    assert "fomo" in tags
    assert "anchoring" in tags
    assert "hallucinated_bias" not in tags
    assert len(tags) == 2


def test_all_invalid_tags_returns_empty():
    """If LLM returns only invalid tags, filtered list is empty."""
    decision = {"ticker": "MSFT", "decision_type": "entry"}
    with patch("shared.llm.call_json", return_value=["foo", "bar", "baz"]):
        tags = auto_tag_biases(decision)
    assert tags == []


# ─────────────────────────────────────────────────────────
# Failure mode handling
# ─────────────────────────────────────────────────────────


def test_llm_exception_returns_empty_list():
    """LLM call fails - graceful degradation to empty tags."""
    decision = {"ticker": "GOOGL", "decision_type": "entry"}
    with patch("shared.llm.call_json", side_effect=RuntimeError("API timeout")):
        tags = auto_tag_biases(decision)
    assert tags == []


def test_unexpected_response_type_returns_empty():
    """LLM returns a string instead of list/dict - safe degradation."""
    decision = {"ticker": "META", "decision_type": "entry"}
    with patch("shared.llm.call_json", return_value="this is not a list"):
        tags = auto_tag_biases(decision)
    assert tags == []


# ─────────────────────────────────────────────────────────
# Prompt construction context
# ─────────────────────────────────────────────────────────


def test_prompt_includes_position_context():
    """When position provided, prompt includes holding details."""
    decision = {"ticker": "NVDA", "decision_type": "scale_in", "reasoning": "Strong AI demand"}
    position = {"qty": 10, "avg_cost": 130.0, "realized_pnl": 0}

    captured_prompt = []

    def capture(prompt, **kwargs):
        captured_prompt.append(prompt)
        return []

    with patch("shared.llm.call_json", side_effect=capture):
        auto_tag_biases(decision, position=position)

    assert len(captured_prompt) == 1
    assert "POSITION CONTEXT" in captured_prompt[0]
    assert "Holding 10" in captured_prompt[0]


def test_prompt_includes_regime_when_provided():
    """When regime context provided, prompt includes it."""
    decision = {"ticker": "BTC", "decision_type": "entry"}

    captured = []

    def capture(prompt, **kwargs):
        captured.append(prompt)
        return []

    with patch("shared.llm.call_json", side_effect=capture):
        auto_tag_biases(decision, regime_str="RISK_OFF, VIX > 30")

    assert "RISK_OFF" in captured[0]


def test_prompt_without_optional_context_omits_those_sections():
    """Minimal decision should produce prompt without POSITION/regime sections."""
    decision = {"ticker": "AAPL", "decision_type": "entry"}

    captured = []

    def capture(prompt, **kwargs):
        captured.append(prompt)
        return []

    with patch("shared.llm.call_json", side_effect=capture):
        auto_tag_biases(decision)

    assert "POSITION CONTEXT" not in captured[0]
    assert "Market regime" not in captured[0]


# ─────────────────────────────────────────────────────────
# BIASES dict structural sanity (catches accidental key drift)
# ─────────────────────────────────────────────────────────


def test_biases_dict_contains_expected_categories():
    """Anti-regression guard: critical bias categories must be present."""
    critical = {"loss_aversion", "fomo", "confirmation_bias", "anchoring", "overconfidence", "sunk_cost"}
    assert critical.issubset(BIASES.keys()), f"Missing critical biases: {critical - BIASES.keys()}"


def test_biases_dict_descriptions_non_empty():
    """Each bias has a non-empty description (for LLM prompt clarity)."""
    for key, desc in BIASES.items():
        assert desc, f"Bias '{key}' has empty description"
        assert len(desc) > 20, f"Bias '{key}' description suspiciously short"
