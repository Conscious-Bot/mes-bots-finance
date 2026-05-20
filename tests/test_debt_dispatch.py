"""Integration tests for intelligence.debt_monitor._dispatch_alerts (H2 audit lock).

Mocks shared.notify.send_text + intelligence.debt_monitor._alerts_enabled.
Covers behavior contract documented in _dispatch_alerts docstring:
- Composite escalation alert content (action playbook present)
- Tier 1 indicator transition with dedup at P3+
- First-ever scan baseline rule (no alert on prev=None)
- Alerts-disabled toggle short-circuits dispatch
- Phase-specific action text propagates correctly
"""
from __future__ import annotations

import pytest

from intelligence.debt_monitor import _dispatch_alerts


@pytest.fixture
def capture_sent(monkeypatch):
    """Capture all notify.send_text calls. Returns the list (filled as side effect)."""
    sent: list[str] = []
    monkeypatch.setattr(
        "shared.notify.send_text",
        lambda txt, **kw: sent.append(txt),
    )
    return sent


@pytest.fixture
def alerts_on(monkeypatch):
    monkeypatch.setattr("intelligence.debt_monitor._alerts_enabled", lambda: True)


@pytest.fixture
def alerts_off(monkeypatch):
    monkeypatch.setattr("intelligence.debt_monitor._alerts_enabled", lambda: False)


def _mk_result(phase: int, score: float, tier1_entries: list[dict] | None = None) -> dict:
    """Build a synthetic run_scan result for dispatch tests."""
    return {
        "phase": phase,
        "score": score,
        "breakdown": {
            1: tier1_entries or [],
            2: [],
            3: [],
        },
        "results": {},
    }


def _tier1_entry(name: str, value: float, phase: int, contribution: float) -> dict:
    return {
        "name": name,
        "value": value,
        "phase": phase,
        "contribution": contribution,
    }


# ============================================================
# Composite escalation scenarios (H1 action playbook injection)
# ============================================================


def test_composite_escalation_p1_to_p2_dispatches_with_action(capture_sent, alerts_on):
    """P1 → P2 transition fires WATCH alert with phase 2 cash+5% action."""
    result = _mk_result(
        phase=2,
        score=42.0,
        tier1_entries=[_tier1_entry("Gold", 4488.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=1, prev_indicator_phases={"Gold": 3})

    assert len(msgs) == 1, "Expected composite escalation only (Gold prev=P3 = no transition)"
    assert len(capture_sent) == 1, "Built messages must all be dispatched"

    msg = capture_sent[0]
    assert "DEBT MONITOR" in msg
    assert "WATCH" in msg, "P2 escalation is WATCH urgency"
    assert "STRESS" in msg, "P2 phase name"
    assert "Cash +5%" in msg, "Phase 2 action playbook present (H1)"
    assert "Active stress drivers" in msg
    assert "Gold" in msg, "Gold P3 driver listed"


def test_composite_escalation_p2_to_p3_is_urgent_with_action(capture_sent, alerts_on):
    """P2 → P3 fires URGENT alert with phase 3 defensive rotation action."""
    result = _mk_result(
        phase=3,
        score=75.0,
        tier1_entries=[_tier1_entry("Gold", 4500.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=2, prev_indicator_phases={"Gold": 3})

    assert len(msgs) == 1
    msg = capture_sent[0]
    assert "URGENT" in msg, "P3+ is URGENT urgency"
    assert "SEVERE" in msg
    assert "Cash +10-15%" in msg, "Phase 3 action playbook (H1)"
    assert "defensive rotation" in msg


def test_composite_escalation_p3_to_p4_crisis_action(capture_sent, alerts_on):
    """P3 → P4 fires URGENT crisis alert with kill leverage action."""
    result = _mk_result(phase=4, score=130.0)
    msgs = _dispatch_alerts(result, prev_composite_phase=3, prev_indicator_phases={})

    assert len(msgs) == 1
    msg = capture_sent[0]
    assert "CRISIS" in msg
    assert "Cash 25%" in msg, "Phase 4 action playbook"
    assert "kill leverage" in msg


# ============================================================
# No-transition / baseline scenarios
# ============================================================


def test_no_transition_no_alert(capture_sent, alerts_on):
    """Same composite phase + no Tier 1 transitions = empty dispatch."""
    result = _mk_result(
        phase=2,
        score=42.0,
        tier1_entries=[_tier1_entry("Gold", 4488.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=2, prev_indicator_phases={"Gold": 3})

    assert msgs == [], "No transition = no message built"
    assert capture_sent == [], "Nothing dispatched"


def test_first_scan_none_prev_no_composite_alert(capture_sent, alerts_on):
    """prev_composite_phase=None (first-ever scan) = baseline, no composite alert even at P3."""
    result = _mk_result(phase=3, score=75.0)
    msgs = _dispatch_alerts(result, prev_composite_phase=None, prev_indicator_phases={})

    composite_msgs = [m for m in msgs if "DEBT MONITOR" in m]
    assert composite_msgs == [], "Baseline establishment: no composite alert on first scan"


# ============================================================
# Tier 1 indicator individual alerts + dedup
# ============================================================


def test_tier1_indicator_transition_to_p3_alerts(capture_sent, alerts_on):
    """Indicator going P1 → P3 fires Tier 1 individual alert (even if composite unchanged)."""
    result = _mk_result(
        phase=2,
        score=42.0,
        tier1_entries=[_tier1_entry("Gold", 4488.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=2, prev_indicator_phases={"Gold": 1})

    assert len(msgs) == 1, "Composite same = no composite alert. Gold P1→P3 = tier alert."
    msg = capture_sent[0]
    assert "TIER 1 ALERT" in msg
    assert "Gold" in msg
    assert "was P1" in msg, "Previous phase reference"


def test_tier1_dedup_no_realert_at_p3(capture_sent, alerts_on):
    """Indicator already at P3 (prev_p >= 3) is NOT re-alerted."""
    result = _mk_result(
        phase=2,
        score=42.0,
        tier1_entries=[_tier1_entry("Gold", 4488.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=2, prev_indicator_phases={"Gold": 3})

    assert msgs == [], "Gold prev=P3 + new=P3 = no transition, dedup holds"
    assert capture_sent == []


def test_tier1_first_observation_at_p3_alerts(capture_sent, alerts_on):
    """Indicator with prev_p=None (never seen) hitting P3 fires alert with 'baseline' label."""
    result = _mk_result(
        phase=2,
        score=42.0,
        tier1_entries=[_tier1_entry("Gold", 4488.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=2, prev_indicator_phases={"Gold": None})

    assert len(msgs) == 1
    msg = capture_sent[0]
    assert "TIER 1 ALERT" in msg
    # prev=None should render as P? or baseline in the message — current impl uses '?'
    assert "?" in msg or "baseline" in msg.lower()


# ============================================================
# Alerts disabled toggle (Phase 2C contract)
# ============================================================


def test_alerts_disabled_short_circuits(capture_sent, alerts_off):
    """When _alerts_enabled() returns False, NO dispatch regardless of escalation."""
    result = _mk_result(
        phase=4,
        score=130.0,
        tier1_entries=[_tier1_entry("Gold", 4488.0, 3, 16.0)],
    )
    msgs = _dispatch_alerts(result, prev_composite_phase=1, prev_indicator_phases={"Gold": 1})

    assert msgs == [], "Disabled: function returns [] immediately"
    assert capture_sent == [], "Nothing sent to Telegram when disabled"
