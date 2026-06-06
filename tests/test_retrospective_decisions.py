"""Tests cron retrospective +30j/+90j sur position_decisions_context."""

import pytest

from intelligence.retrospective_decisions import _classify_verdict


def test_classify_neutral_small_outcome():
    """|outcome| < 3% = neutral peu importe alignement."""
    v = _classify_verdict(
        outcome_pct=1.5, pnl_pct=1.5,
        regime_warnings_json="[]", bias_warnings_json="[]",
    )
    assert v == "neutral"


def test_classify_aligned_positive():
    """Aucune warning au moment decision + outcome positif => aligned_positive."""
    v = _classify_verdict(
        outcome_pct=10.0, pnl_pct=10.0,
        regime_warnings_json="[]", bias_warnings_json="[]",
    )
    assert v == "aligned_positive"


def test_classify_aligned_negative():
    """Aucune warning + outcome négatif => système n'avait pas vu, signal failed."""
    v = _classify_verdict(
        outcome_pct=-15.0, pnl_pct=-15.0,
        regime_warnings_json="[]", bias_warnings_json="[]",
    )
    assert v == "aligned_negative"


def test_classify_against_positive():
    """Avait warning macro + outcome positif => gut beat signal."""
    v = _classify_verdict(
        outcome_pct=20.0, pnl_pct=20.0,
        regime_warnings_json='[{"rule_id": "R1_semis_concentration", "severity": "high"}]',
        bias_warnings_json="[]",
    )
    assert v == "against_positive"


def test_classify_against_negative():
    """Avait warning + outcome négatif => système avait raison."""
    v = _classify_verdict(
        outcome_pct=-12.0, pnl_pct=-12.0,
        regime_warnings_json='[{"rule_id": "R1_semis_concentration", "severity": "high"}]',
        bias_warnings_json="[]",
    )
    assert v == "against_negative"


def test_classify_bias_warning_counts_as_against():
    """Lock_in/fomo bias warning = signal contre, outcome negatif = against_negative."""
    v = _classify_verdict(
        outcome_pct=-8.0, pnl_pct=-8.0,
        regime_warnings_json="[]",
        bias_warnings_json='["LOCK_IN risk : tu vends un winner..."]',
    )
    assert v == "against_negative"


def test_classify_invalid_json_safe():
    """JSON corrupted = traite comme empty (graceful degrade)."""
    v = _classify_verdict(
        outcome_pct=10.0, pnl_pct=10.0,
        regime_warnings_json="not json",
        bias_warnings_json="also not json",
    )
    assert v == "aligned_positive"


def test_classify_sell_action_pnl_logic():
    """SELL avec outcome positif (prix monté) = mauvais pnl pour seller
    (would have made more by holding). Test direct via pnl_pct."""
    # Sell at 100, price went to 110 (+10% outcome). PnL signed = -10% (loss for seller).
    v = _classify_verdict(
        outcome_pct=10.0, pnl_pct=-10.0,
        regime_warnings_json="[]", bias_warnings_json="[]",
    )
    assert v == "aligned_negative"  # pnl_pct < 0 = negative for the seller


@pytest.mark.live_data
def test_summary_by_verdict_empty():
    """Smoke : summary_by_verdict returns dict (empty si pas de retrospectives)."""
    from intelligence.retrospective_decisions import summary_by_verdict
    s = summary_by_verdict(30)
    assert isinstance(s, dict)
