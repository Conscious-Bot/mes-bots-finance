"""Display-layer tests for risk_manager.format_risk_check_display.

No LLM mocking required - tests verify display rendering of flip_criteria
under various result-dict states.

Audit-grade per High Standard Mode (PHILOSOPHY.md): display logic tested
independently of LLM behavior.
"""

from intelligence.risk_manager import format_risk_check_display


def _base_result():
    return {
        "verdict": "conditional",
        "concerns": ["concern 1"],
        "counter_proposal": {"size_usd": 500, "size_reasoning": "trim", "conditions": []},
        "stress_scenario": {"scenario": "drawdown 20%", "portfolio_impact_pct": -3.5},
        "thesis_alignment": "no active thesis",
        "thesis_alignment_detail": "...",
        "bias_flags": ["fomo"],
        "signal_citations": [],
        "flip_criteria": [],
        "reasoning": "summary",
    }


def test_flip_criteria_renders_when_present():
    result = _base_result()
    result["flip_criteria"] = [
        "if NVDA Q1 FY27 DC revenue YoY < +30%",
        "if hyperscaler capex cuts >$30B announced 90d",
        "if H200 export controls expand Q3",
    ]
    out = format_risk_check_display(result, "NVDA", "long", 1000)
    assert "FLIP CRITERIA" in out
    assert "NVDA Q1 FY27 DC revenue YoY" in out
    assert "hyperscaler capex" in out
    assert "H200 export controls" in out


def test_flip_criteria_absent_when_empty():
    result = _base_result()
    result["flip_criteria"] = []
    out = format_risk_check_display(result, "NVDA", "long", 1000)
    assert "FLIP CRITERIA" not in out


def test_flip_criteria_absent_when_missing_key():
    result = _base_result()
    del result["flip_criteria"]
    out = format_risk_check_display(result, "NVDA", "long", 1000)
    assert "FLIP CRITERIA" not in out


def test_flip_criteria_caps_at_4():
    result = _base_result()
    result["flip_criteria"] = [f"criterion {i}" for i in range(10)]
    out = format_risk_check_display(result, "NVDA", "long", 1000)
    assert out.count("  -> criterion") == 4


def test_error_verdict_short_circuits_no_flip_render():
    result = {"verdict": "error", "reasoning": "LLM failed"}
    out = format_risk_check_display(result, "NVDA", "long", 1000)
    assert "Risk check failed" in out
    assert "FLIP CRITERIA" not in out
