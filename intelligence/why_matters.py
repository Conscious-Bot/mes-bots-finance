"""
Phase 11 — LLM "why this matters NOW" annotator.
Takes a scored signal + regime context, returns 1 sentence (max 30 words).
Used to annotate top-3 daily digest signals.
"""
import logging

from shared import llm

log = logging.getLogger(__name__)


def _build_prompt(signal, score_dict, regime_info):
    derived = score_dict.get("_derived", {}) or {}
    tickers = derived.get("tickers", []) or []
    primary = tickers[0] if tickers else "n/a"
    other = ", ".join(tickers[1:]) if len(tickers) > 1 else "n/a"
    narratives = ", ".join(derived.get("narratives", []) or []) or "n/a"

    summary = (signal.get("summary") or signal.get("title") or "")[:500]

    credit = (regime_info or {}).get("credit", {}) or {}
    if isinstance(credit, dict):
        credit_overall = credit.get("overall", "NORMAL")
        hy_bp = (credit.get("hy") or {}).get("bp")
    else:
        credit_overall = "NORMAL"
        hy_bp = None
    credit_line = "Credit regime: " + credit_overall
    if hy_bp:
        credit_line += " (HY OAS " + (f"{hy_bp:.0f}") + "bp)"

    overall = (regime_info or {}).get("overall", "unknown")

    return (
        "You are a senior buy-side analyst. Given this signal, write ONE sentence (max 30 words) "
        "explaining why it matters NOW given the current market regime.\n\n"
        "Signal:\n"
        "- Summary: " + summary + "\n"
        "- Primary ticker: " + primary + "\n"
        "- Other tickers: " + other + "\n"
        "- Type: " + (derived.get("signal_type") or "n/a") + "\n"
        "- Polarity: " + (derived.get("polarity") or "n/a") + "\n"
        "- Narratives: " + narratives + "\n\n"
        "Context:\n"
        "- Materiality: " + ("{:.3f}".format(score_dict.get("composite", 0))) +
        " (novelty " + ("{:.2f}".format(score_dict.get("novelty", 0))) +
        ", cross-conf " + ("{:.2f}".format(score_dict.get("cross_confirmation", 0))) +
        ", impact " + ("{:.2f}".format(score_dict.get("market_impact", 0))) +
        ", regime-fit " + ("{:.2f}".format(score_dict.get("regime_relevance", 0))) + ")\n"
        "- Macro regime: " + str(overall) + "\n"
        "- " + credit_line + "\n\n"
        "Rules:\n"
        "- ONE sentence, max 30 words.\n"
        "- Specific actionable implication, not vague hedging.\n"
        "- Reference regime context if directly relevant.\n"
        "- No fluff, no 'this could be important', no 'investors should consider'.\n"
        "- Match the language of the Summary (French or English).\n\n"
        "Why this matters NOW:"
    )


def generate_why_matters(signal, score_dict, regime_info=None):
    """Generate 1-sentence 'why this matters now' annotation via LLM.
    Returns str (max ~30 words). Returns short error tag on LLM failure."""
    try:
        prompt = _build_prompt(signal, score_dict, regime_info or {})
        result = llm.call(prompt, max_tokens=120, task="why_matters")
        return (result or "").strip()
    except Exception as e:
        log.warning("why_matters failed: " + str(e))
        return ""
