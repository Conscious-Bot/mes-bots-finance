"""Phase B7 — Pre-mortem auto-generation on thesis creation (Opus tier='synthesize').

The investor decides to open a thesis. BEFORE the position is built, Opus imagines
the thesis fails at 12 months and articulates the 5 most plausible failure modes
with probabilities, signals to monitor, and mitigation actions.

This is the structural antidote to optimism bias + post-hoc rationalization.
Forces exit discipline pre-commit. Anti loss-aversion + anti hold-too-long.
"""

import json
import logging

log = logging.getLogger(__name__)

PROMPT = """You are a behavioral finance advisor performing a PRE-MORTEM on a fresh trading thesis.

The investor has just decided to open this thesis. Your job: imagine that 12 months from NOW, this thesis HAS FAILED — either lost money or failed to deliver. Generate the 5 most PLAUSIBLE failure scenarios. Be specific to the ticker, not generic.

THESIS:
- Ticker: {ticker}
- Direction: {direction}
- Horizon: {horizon}
- Conviction (1-5): {conviction}
- Entry price: ${entry_price}
- Target partial: ${target_partial}
- Target full: ${target_full}
- Stop/invalidation level: ${stop_price}

KEY DRIVERS (investor's reasons FOR):
{drivers}

INVALIDATION TRIGGERS (investor's defined stop conditions):
{invalidation}

CONTEXT:
- Market regime: {regime}
- Credit regime: {credit_regime}

OUTPUT REQUIREMENTS — return JSON only (no markdown, no preamble):
{{
  "failure_modes": [
    {{
      "scenario": "Concrete narrative of what happens (1-2 sentences, ticker-specific)",
      "probability": 0.XX,
      "signals_to_monitor": ["concrete leading indicator 1", "concrete leading indicator 2"],
      "mitigation": "Specific action the investor would take if this scenario starts unfolding"
    }}
    // exactly 5 entries
  ],
  "overall_assessment": "1-2 sentence summary of the SINGLE biggest fragility of this thesis",
  "asymmetry_warning": "If upside potential is meaningfully smaller than downside potential, articulate why. Else null."
}}

Be specific (mention real catalysts, real numbers, real comparable assets). Avoid platitudes."""


def generate_pre_mortem(thesis):
    """Run Opus pre-mortem. Returns JSON string or None on failure."""
    from shared import llm

    try:
        drivers = thesis.get("key_drivers") or []
        if isinstance(drivers, str):
            try:
                drivers = json.loads(drivers)
            except Exception:
                drivers = [drivers]
        invalidation = thesis.get("invalidation_triggers") or []
        if isinstance(invalidation, str):
            try:
                invalidation = json.loads(invalidation)
            except Exception:
                invalidation = [invalidation]

        prompt = PROMPT.format(
            ticker=thesis.get("ticker", "?"),
            direction=thesis.get("direction", "?"),
            horizon=thesis.get("horizon", "medium"),
            conviction=thesis.get("conviction", "?"),
            entry_price=thesis.get("entry_price", "?"),
            target_partial=thesis.get("target_partial", "n/a"),
            target_full=thesis.get("target_full", "n/a"),
            stop_price=thesis.get("stop_price", "n/a"),
            drivers="\n".join(f"- {d}" for d in drivers) or "(none)",
            invalidation="\n".join(f"- {t}" for t in invalidation) or "(none)",
            regime=thesis.get("regime") or "unknown",
            credit_regime=thesis.get("credit_regime") or "unknown",
        )
        result = llm.call_json(prompt, tier="synthesize", max_tokens=2000)
        if isinstance(result, dict) and "failure_modes" in result:
            return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        log.warning(f"pre_mortem generation failed: {e}")
    return None


def format_pre_mortem_display(pm_json_str, max_len_per_field=220):
    """Format pre-mortem JSON for Telegram display."""
    if not pm_json_str:
        return None
    try:
        pm = json.loads(pm_json_str)
    except Exception:
        return None

    lines = ["PRE-MORTEM — 5 failure modes"]
    for i, fm in enumerate(pm.get("failure_modes", [])[:5], 1):
        p = fm.get("probability", 0)
        if isinstance(p, (int, float)):
            p_str = f"P={p:.0%}"
        else:
            p_str = f"P={p}"
        sc = (fm.get("scenario") or "")[:max_len_per_field]
        lines.append(f"\n{i}. {p_str} — {sc}")
        sigs = fm.get("signals_to_monitor") or []
        if sigs:
            lines.append("   Monitor: " + "; ".join(s[:50] for s in sigs[:3]))
        mit = (fm.get("mitigation") or "")[:max_len_per_field]
        if mit:
            lines.append(f"   Action: {mit}")

    overall = pm.get("overall_assessment")
    if overall:
        lines.append(f"\nKey fragility: {overall[:200]}")
    asym = pm.get("asymmetry_warning")
    if asym and asym != "null":
        lines.append(f"\nASYMMETRY WARNING: {asym[:200]}")
    return "\n".join(lines)
