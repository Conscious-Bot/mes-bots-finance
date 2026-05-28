"""Phase C12 — Risk Management layer (TradingAgents pattern light).

Single dedicated Opus call that challenges a proposed trade against the actual
portfolio state: sizing, concentration, correlation, time horizon mismatch,
stress scenarios, thesis alignment, behavioral bias flags.

Distinct from /analyze and /analyze_debate (which produce a verdict but don't
challenge sizing). This is the discipline layer between conviction and execution.

Aligned with Olivier's behavioral profile: counters "tient trop long crypto tops"
by surfacing concentration before scale-up; counters "vend trop tôt winners" by
flagging timing-discipline traps.
"""

import contextlib
import logging

from shared.storage import build_signals_context_block

log = logging.getLogger(__name__)


RISK_PROMPT = """You are a SHARP, DIRECT portfolio risk manager. Challenge this proposed trade. Be BLUNT, no hedging language. Identify the strongest concerns, propose specific counter-actions when warranted.

PROPOSED TRADE:
- Ticker: {ticker}
- Side: {side}
- Proposed size: ${proposed_usd:,.0f}
- Reasoning given: "{reasoning}"

CURRENT PORTFOLIO STATE:
{portfolio_state}

ACTIVE THESIS (if any):
{thesis_state}

RECENT DECISIONS ON THIS TICKER (last 90d):
{decisions_state}

BIAS PATTERNS (your historical aggregate on this ticker):
{bias_state}

RECENT NEWSLETTER SIGNALS ON {ticker} (last 30d, weighted by source credibility * materiality):
{signals_state}

MARKET REGIME:
- Macro: {macro_regime}
- Credit: {credit_regime}

YOUR JOB — challenge on 8 axes:
1. **Concentration**: would this trade push single-name or sector exposure beyond reasonable limits?
2. **Correlation**: does this add concentration with existing positions (e.g. another AI/semis name)?
3. **Time horizon**: does this trade timeframe match the active thesis or contradict it?
4. **Stress scenario**: if this goes -20% in 3 months, what's the portfolio impact?
5. **Thesis alignment**: aligned with the active thesis triggers, or off-script?
6. **Bias flag**: does this trade pattern-match known cognitive biases (anchoring, fomo, sunk_cost, etc.)?
7. **Signal context**: do recent high-credibility newsletter signals SUPPORT or CONTRADICT this trade? If signals lean bearish but trade is bullish (or vice versa), flag explicitly. Cite top 2-3 in concerns or reasoning.
8. **Flip criteria (bidirectional discipline)**: After your verdict, name 2-3 SPECIFIC, MEASURABLE, TIME-BOUNDED developments that would FLIP your verdict to the opposite stance. If APPROVED/CONDITIONAL → what evidence would force REJECTED? If REJECTED → what would force APPROVED? Each must be (a) concrete data point / price level / event, (b) bounded in time (within 30d / 90d / 6m), (c) plausibly observable. NOT generic ("if fundamentals change"). YES specific ("if NVDA Q1 FY27 DC revenue YoY <+30%" or "if HBM supply doubles by Q3 FY27"). This is the bidirectional discipline check.

OUTPUT JSON ONLY (no markdown):
{{
  "verdict": "approved" | "conditional" | "rejected",
  "concerns": ["concrete concern 1", "concrete concern 2", ...],
  "counter_proposal": {{
    "size_usd": <number or null>,
    "size_reasoning": "...",
    "conditions": ["condition 1", "condition 2", ...]
  }},
  "stress_scenario": {{
    "scenario": "specific narrative",
    "portfolio_impact_pct": <number, negative for loss>
  }},
  "thesis_alignment": "aligned" | "partially aligned" | "contradicted" | "no active thesis",
  "thesis_alignment_detail": "1-sentence explanation",
  "bias_flags": ["bias_name1", "bias_name2"],
  "signal_citations": ["Source Tier X cred 0.XX -> [sentiment] short cite [YYYY-MM-DD]"],
  "flip_criteria": ["specific measurable bounded event 1", "...", "..."],
  "reasoning": "1-3 sentences blunt summary"
}}

Be concrete. No platitudes. If the trade is fine, say "approved" with brief justification."""


def _build_portfolio_state(positions):
    if not positions:
        return "No active positions. This would be the first exposure."
    # ADR 005: avg_cost EUR canonical -> convert to USD for prompt currency
    # coherence (RISK_PROMPT uses proposed_usd and USD-denominated prices throughout).
    from shared.positions import cost_in

    rows = []
    for p in positions:
        qty = p.get("qty", 0) or 0
        avg_usd = cost_in(p.get("avg_cost", 0) or 0, "USD") or 0
        rows.append((p["ticker"], qty, avg_usd, qty * avg_usd))
    total_book_usd = sum(val for _, _, _, val in rows)
    lines = [f"Total long book at cost basis: ${total_book_usd:,.0f}"]
    lines.append("Positions:")
    for ticker, qty, avg_usd, val in rows:
        pct = (val / total_book_usd * 100) if total_book_usd > 0 else 0
        lines.append(f"  - {ticker}: {qty} @ ${avg_usd:.2f} (${val:,.0f}, {pct:.1f}%)")
    return "\n".join(lines)


def _build_thesis_state(thesis):
    if not thesis:
        return "No active thesis on this ticker."
    # ADR 005 P2 (Day 14): theses prices EUR canonical (cross-source ratio audit
    # confirmed ~1.0 across all 4 native currencies). Convert to USD for prompt
    # currency coherence with rest of RISK_PROMPT.
    from shared.positions import cost_in

    def _u(field):
        v = thesis.get(field)
        return cost_in(v, "USD") if v is not None else None

    entry_u = _u("entry_price")
    partial_u = _u("target_partial")
    full_u = _u("target_full")
    stop_u = _u("stop_price")

    def _fmt(x):
        return f"${x:.2f}" if x is not None else "n/a"

    parts = [
        f"Direction: {thesis.get('direction')}",
        f"Conviction: {thesis.get('conviction')}",
        f"Entry: {_fmt(entry_u)}",
        f"Target partial: {_fmt(partial_u)}",
        f"Target full: {_fmt(full_u)}",
        f"Stop: {_fmt(stop_u)}",
    ]
    return "\n".join(parts)


def _build_decisions_state(decisions):
    if not decisions:
        return "None."
    lines = []
    for d in decisions[:5]:
        lines.append(
            f"  - {d.get('created_at', '')[:10]} {d.get('decision_type')} conf={d.get('confidence_pre')} @ ${d.get('price_at_decision')}"
        )
    return "\n".join(lines)


def _build_bias_state(stats):
    if not stats or stats.get("total_with_tags", 0) == 0:
        return "No bias data yet."
    top = sorted(stats.get("bias_counts", []), key=lambda x: -x[1])[:5]
    return ", ".join(f"{tag} (n={n})" for tag, n in top)


def run_risk_check(ticker, side, proposed_usd, reasoning):
    """Run risk check on a proposed trade. Returns dict with verdict + analysis."""
    from shared import llm, storage

    positions = storage.get_active_positions() or []
    thesis = storage.get_thesis_by_ticker(ticker, status="active")
    decisions = []
    with contextlib.suppress(Exception):
        decisions = storage.get_decisions_for_ticker(ticker, since_days=90, limit=10)
    bias_stats = storage.get_bias_stats(ticker=ticker, since_days=180)

    # Regime context
    macro_regime = "unknown"
    credit_regime = "unknown"
    try:
        from shared import macro

        macro_regime = macro.current_regime_text() if hasattr(macro, "current_regime_text") else "unknown"
    except Exception:
        pass
    try:
        from shared import macro

        if hasattr(macro, "current_credit_regime"):
            credit_regime = macro.current_credit_regime()
    except Exception:
        pass

    prompt = RISK_PROMPT.format(
        ticker=ticker.upper(),
        side=side,
        proposed_usd=proposed_usd,
        reasoning=reasoning or "(none provided)",
        portfolio_state=_build_portfolio_state(positions),
        thesis_state=_build_thesis_state(thesis),
        decisions_state=_build_decisions_state(decisions),
        bias_state=_build_bias_state(bias_stats),
        signals_state=build_signals_context_block(ticker),
        macro_regime=macro_regime,
        credit_regime=credit_regime,
    )

    try:
        result = llm.call_json(prompt, tier="synthesize", max_tokens=1500)
        if not isinstance(result, dict) or "verdict" not in result:
            return {"verdict": "error", "reasoning": "LLM returned invalid structure", "raw": result}
        return result
    except Exception as e:
        log.warning(f"risk_check {ticker} failed: {e}")
        return {"verdict": "error", "reasoning": f"LLM call failed: {e}"}


def format_risk_check_display(result, ticker, side, proposed_usd):
    """Format for Telegram."""
    if result.get("verdict") == "error":
        return f"Risk check failed: {result.get('reasoning')}"
    verdict = result.get("verdict", "unknown").upper()
    icon = {"APPROVED": "🟢", "CONDITIONAL": "🟡", "REJECTED": "🔴"}.get(verdict, "?")
    lines = [f"{icon} RISK CHECK — {ticker.upper()} {side.upper()} ${proposed_usd:,.0f}"]
    lines.append(f"Verdict: {verdict}")
    lines.append("")
    concerns = result.get("concerns") or []
    if concerns:
        lines.append("CONCERNS:")
        for c in concerns[:6]:
            lines.append(f"  - {c}")
        lines.append("")
    cp = result.get("counter_proposal") or {}
    if cp.get("size_usd") is not None:
        lines.append("COUNTER-PROPOSAL:")
        lines.append(f"  Size: ${cp.get('size_usd'):,.0f}")
        if cp.get("size_reasoning"):
            lines.append(f"  Why: {cp.get('size_reasoning')}")
        for cond in (cp.get("conditions") or [])[:5]:
            lines.append(f"  • {cond}")
        lines.append("")
    stress = result.get("stress_scenario") or {}
    if stress.get("scenario"):
        impact = stress.get("portfolio_impact_pct")
        impact_str = f"{impact:+.1f}%" if isinstance(impact, (int, float)) else "?"
        lines.append(f"STRESS: {stress.get('scenario')} → portfolio {impact_str}")
        lines.append("")
    align = result.get("thesis_alignment", "?")
    lines.append(f"THESIS ALIGNMENT: {align}")
    if result.get("thesis_alignment_detail"):
        lines.append(f"  {result.get('thesis_alignment_detail')}")
    biases = result.get("bias_flags") or []
    if biases:
        lines.append(f"BIAS FLAGS: {', '.join(biases)}")
    lines.append("")
    lines.append(f"REASONING: {result.get('reasoning', '')}")
    flip = result.get("flip_criteria") or []
    if flip:
        lines.append("")
        lines.append("FLIP CRITERIA (what would invalidate this verdict):")
        for f in flip[:4]:
            lines.append(f"  -> {f}")
    return "\n".join(lines)
