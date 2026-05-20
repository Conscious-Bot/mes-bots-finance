"""Phase B6 — Auto-classify cognitive biases on trading decisions via Haiku LLM."""

import logging
from typing import Any

log = logging.getLogger(__name__)

BIASES = {
    "anchoring": "Anchored on specific price reference (prior high, entry price, round number)",
    "recency_bias": "Over-weighting recent news/moves vs longer-term context",
    "confirmation_bias": "Decision aligns with existing thesis/position without challenging evidence",
    "fomo": "Buying on momentum / missed-out feeling, not thesis-based",
    "narrative_capture": "Following popular story uncritically, no independent validation",
    "loss_aversion": "Avoiding realized loss / holding loser too long / disposition effect",
    "regret_avoidance": "Decision driven by anticipating future regret",
    "overconfidence": "Conviction higher than warranted by evidence quality",
    "sunk_cost": "Holding due to prior investment, not forward prospects",
    "availability_heuristic": "Over-weighting easily-recalled examples (recent news, vivid stories)",
}


def auto_tag_biases(decision: dict[str, Any], position: dict[str, Any] | None = None, regime_str: str | None = None, top_signals: list[Any] | None = None) -> list[str]:
    """Return list of bias tags applicable to a decision. Empty if no clear bias detected."""
    from shared import llm

    bias_lines = "\n".join(f"- {k}: {v}" for k, v in BIASES.items())

    parts = [
        "You are a behavioral finance expert tagging cognitive biases in trading decisions.",
        "",
        "DECISION:",
        f"Ticker: {decision.get('ticker', '?')}",
        f"Type: {decision.get('decision_type', '?')}",
        f"Confidence (1-5): {decision.get('confidence_pre', '?')}",
        f"Direction: {decision.get('direction', 'long')}",
        f"Price at decision: ${decision.get('price_at_decision') or 'n/a'}",
        f'Reasoning: "{(decision.get("reasoning") or "")[:500]}"',
    ]
    if position:
        parts.append("")
        parts.append("POSITION CONTEXT:")
        # ADR 005: avg_cost EUR canonical -> convert to USD for prompt coherence.
        # realized_pnl currency convention not audited (out of ADR 005 scope).
        from shared.positions import cost_in
        avg_usd = cost_in(position.get("avg_cost"), "USD") or 0
        parts.append(
            f"Holding {position.get('qty')} @ avg ${avg_usd:.2f}, realized PnL ${position.get('realized_pnl', 0):.2f}"
        )
    if regime_str:
        parts.append(f"Market regime: {regime_str}")
    if top_signals:
        parts.append(f"Recent top signals for ticker: {top_signals[:3]}")
    parts.append("")
    parts.append("BIASES TO CONSIDER (only tag where EVIDENCE in reasoning supports it, be conservative):")
    parts.append(bias_lines)
    parts.append("")
    parts.append(
        "Return JSON array of applicable bias tags (or [] if none clearly apply). NO markdown, JSON array only."
    )
    parts.append('Examples: ["anchoring", "loss_aversion"] OR ["fomo"] OR []')

    prompt = "\n".join(parts)
    try:
        result = llm.call_json(prompt, tier="extract", max_tokens=120)
        if isinstance(result, list):
            return [t for t in result if t in BIASES]
        if isinstance(result, dict):
            tags = result.get("tags") or result.get("biases") or []
            if isinstance(tags, list):
                return [t for t in tags if t in BIASES]
    except Exception as e:
        log.warning(f"bias_tagger failed: {e}")
    return []
