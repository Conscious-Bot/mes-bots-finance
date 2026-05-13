"""Phase 5 deep clean - integration tests on pure-logic intelligence functions.

Targets modules at 0-10% coverage with NO LLM/DB dependencies:
- intelligence.journal: thesis_relative_position, auto_classify_mistake, format_decision_summary
- intelligence.thesis: format_thesis_card, build_revisit_questions

All tests pure (no monkeypatch, no fixtures), execute in <100ms total.
"""

from intelligence.journal import (
    auto_classify_mistake,
    format_decision_summary,
    thesis_relative_position,
)
from intelligence.thesis import build_revisit_questions, format_thesis_card

# ─────────────────────────────────────────────────────────
# thesis_relative_position — categorical price-vs-thesis label
# ─────────────────────────────────────────────────────────

def test_thesis_position_at_or_above_full_target():
    thesis = {"entry_price": 100, "target_partial": 130, "target_full": 160, "stop_price": 85}
    assert thesis_relative_position(170, thesis) == "at_or_above_full_target"

def test_thesis_position_between_partial_and_full():
    thesis = {"entry_price": 100, "target_partial": 130, "target_full": 160, "stop_price": 85}
    assert thesis_relative_position(145, thesis) == "between_partial_and_full"

def test_thesis_position_at_partial_no_full():
    thesis = {"entry_price": 100, "target_partial": 130, "stop_price": 85}
    assert thesis_relative_position(135, thesis) == "at_or_above_partial"

def test_thesis_position_below_entry():
    thesis = {"entry_price": 100, "target_partial": 130, "target_full": 160, "stop_price": 85}
    assert thesis_relative_position(90, thesis) == "below_entry"

def test_thesis_position_at_or_below_stop_no_entry():
    """at_or_below_stop fires when entry not set (below_entry takes priority otherwise)."""
    thesis = {"stop_price": 85}
    assert thesis_relative_position(80, thesis) == "at_or_below_stop"

def test_thesis_position_below_entry_dominates_stop():
    """Documented priority: below_entry wins over at_or_below_stop when both apply."""
    thesis = {"entry_price": 100, "stop_price": 85}
    assert thesis_relative_position(80, thesis) == "below_entry"

def test_thesis_position_between_entry_and_partial():
    thesis = {"entry_price": 100, "target_partial": 130, "target_full": 160, "stop_price": 85}
    assert thesis_relative_position(115, thesis) == "between_entry_and_partial"

def test_thesis_position_missing_inputs():
    assert thesis_relative_position(0, {}) is None
    assert thesis_relative_position(100, None) is None
    assert thesis_relative_position(None, {"entry_price": 100}) is None


# ─────────────────────────────────────────────────────────
# auto_classify_mistake — categorical mistake-type for journal
# ─────────────────────────────────────────────────────────

def test_classify_entry_correct_long():
    """Long entry with +10% return = correct."""
    decision = {"price_at_decision": 100, "decision_type": "entry", "direction": "long"}
    assert auto_classify_mistake(decision, 110, 30) == "entry_correct"

def test_classify_entry_premature_long():
    """Long entry that drops -15% = premature."""
    decision = {"price_at_decision": 100, "decision_type": "entry", "direction": "long"}
    assert auto_classify_mistake(decision, 85, 30) == "entry_premature"

def test_classify_entry_flat_long():
    """Long entry small move (-3%) = flat."""
    decision = {"price_at_decision": 100, "decision_type": "entry", "direction": "long"}
    assert auto_classify_mistake(decision, 97, 30) == "entry_flat"

def test_classify_sold_too_early():
    """partial_exit at 100 then price hits 115 = sold too early (key bias!)."""
    decision = {"price_at_decision": 100, "decision_type": "partial_exit", "direction": "long"}
    assert auto_classify_mistake(decision, 115, 30) == "sold_too_early"

def test_classify_correct_exit():
    """full_exit at 100 then price drops to 90 = correct exit."""
    decision = {"price_at_decision": 100, "decision_type": "full_exit", "direction": "long"}
    assert auto_classify_mistake(decision, 90, 30) == "correct_exit"

def test_classify_unresolvable_no_price():
    """Missing price_at_decision returns unresolvable."""
    decision = {"decision_type": "entry", "direction": "long"}
    assert auto_classify_mistake(decision, 110, 30) == "unresolvable_no_price"

def test_classify_short_entry_correct():
    """Short entry then -10% = correct (short profits when price falls)."""
    decision = {"price_at_decision": 100, "decision_type": "entry", "direction": "short"}
    assert auto_classify_mistake(decision, 90, 30) == "entry_correct"


# ─────────────────────────────────────────────────────────
# format_decision_summary — string output sanity
# ─────────────────────────────────────────────────────────

def test_format_decision_summary_returns_nonempty_string():
    d = {"id": 1, "ticker": "NVDA", "decision_type": "entry", "direction": "long",
         "price_at_decision": 130.0, "reasoning": "Strong AI demand"}
    result = format_decision_summary(d)
    assert isinstance(result, str)
    assert len(result) > 0


# ─────────────────────────────────────────────────────────
# thesis.format_thesis_card — Telegram markdown output
# ─────────────────────────────────────────────────────────

def test_format_thesis_card_includes_ticker_and_conviction():
    thesis = {"ticker": "NVDA", "direction": "long", "conviction": 4, "status": "active",
              "entry_price": 130, "target_partial": 180, "target_full": 250,
              "horizon": "6-12mo", "opened_at": "2026-05-13"}
    card = format_thesis_card(thesis)
    assert "NVDA" in card
    assert "conviction 4/5" in card
    assert "ACTIVE" in card
    assert "$130" in card
    assert "$180" in card
    assert "$250" in card

def test_format_thesis_card_minimal_thesis():
    """Even with bare minimum fields, doesn't crash."""
    thesis = {"ticker": "AAPL", "direction": "long", "conviction": 3, "status": "active",
              "entry_price": 200}
    card = format_thesis_card(thesis)
    assert "AAPL" in card
    assert "conviction 3/5" in card

def test_format_thesis_card_with_drivers_and_invalidation():
    thesis = {"ticker": "NVDA", "direction": "long", "conviction": 4, "status": "active",
              "entry_price": 130, "key_drivers": ["AI capex", "Datacenter growth"],
              "invalidation_triggers": ["DC capex decline >20%"]}
    card = format_thesis_card(thesis)
    assert "AI capex" in card
    assert "DC capex decline" in card
    assert "Drivers" in card
    assert "Invalidation" in card


# ─────────────────────────────────────────────────────────
# thesis.build_revisit_questions — returns list of probing questions
# ─────────────────────────────────────────────────────────

def test_build_revisit_questions_returns_string_with_3_questions():
    thesis = {"id": 1, "ticker": "NVDA", "direction": "long", "conviction": 4,
              "key_drivers": ["AI capex"], "invalidation_triggers": ["DC slowdown"]}
    text = build_revisit_questions(thesis)
    assert isinstance(text, str)
    assert "Question 1" in text
    assert "Question 2" in text
    assert "Question 3" in text
    assert "NVDA" in text
    assert "conviction 4/5" in text
    assert "AI capex" in text
    assert "DC slowdown" in text
    assert "/thesis_note 1" in text
