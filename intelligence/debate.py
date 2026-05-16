"""Phase C11 — Multi-round Bull/Bear adversarial debate with convergence detection.

Pattern TradingAgents : 3 rounds dialectique au lieu de single-shot synthesis.
- Round 1: Bull + Bear posent thèses en parallèle (2 Sonnet calls)
- Round 2: Bull challenges Bear's R1, vice-versa (2 Sonnet calls)
- Round 3: Final positions (2 Sonnet calls)
- Convergence: BGE-small embedding cosine entre R3 conclusions
  > 0.7 = CONVERGED (high conviction signal)
  0.4-0.7 = MODERATE
  < 0.4 = DIVERGED (complexity flag, requires human attention)
"""

import logging

log = logging.getLogger(__name__)


ROUND_1_BULL = """You are a sharp BULL analyst on {ticker}.

CONTEXT:
{context}

Argue the strongest case for LONG {ticker} over 6-12 months. Be SPECIFIC, use the data above (numbers, names, dates). Avoid platitudes. 250 words max.

OUTPUT FORMAT:
DRIVERS:
1. [driver with concrete evidence from data]
2. [...]
3. [...]
RISKS YOU ACKNOWLEDGE (intellectual honesty):
- [...]
- [...]
THESIS SUMMARY (1 sentence):
[...]"""


ROUND_1_BEAR = """You are a sharp BEAR analyst on {ticker}.

CONTEXT:
{context}

Argue the strongest case AGAINST {ticker} over 6-12 months — short, avoid, or expect material underperformance. Be SPECIFIC, use the data above. Avoid platitudes. 250 words max.

OUTPUT FORMAT:
CONCERNS:
1. [concern with concrete evidence]
2. [...]
3. [...]
COUNTERS YOU ACKNOWLEDGE (intellectual honesty):
- [...]
- [...]
THESIS SUMMARY (1 sentence):
[...]"""


ROUND_2_BULL = """You are the same BULL analyst. The BEAR just argued:

{bear_r1}

Specifically engage the BEAR's STRONGEST concern. Either defend with evidence or update your thesis honestly if the concern is valid. No hand-waving. 200 words max.

OUTPUT:
THE BEAR'S STRONGEST POINT: [which one and why]
YOUR RESPONSE: [defend or concede + reason]
UPDATED THESIS (if any): [...]
CURRENT BULL CONFIDENCE 1-10: [N]"""


ROUND_2_BEAR = """You are the same BEAR analyst. The BULL just argued:

{bull_r1}

Specifically engage the BULL's STRONGEST driver. Either counter with evidence or update your thesis honestly if the driver is valid. No hand-waving. 200 words max.

OUTPUT:
THE BULL'S STRONGEST POINT: [which one and why]
YOUR RESPONSE: [counter or concede + reason]
UPDATED THESIS (if any): [...]
CURRENT BEAR CONFIDENCE 1-10: [N]"""


ROUND_3_BULL = """You are the BULL. After 2 rounds, finalize.

YOUR ROUND 2: {bull_r2}
BEAR'S ROUND 2: {bear_r2}

Provide FINAL position. If you've updated significantly, state it explicitly. 150 words max.

FINAL BULL POSITION:
[clear stance]
CONFIDENCE (1-10): [N]
RECOMMENDED ACTION: [LONG / WAIT / AVOID]"""


ROUND_3_BEAR = """You are the BEAR. After 2 rounds, finalize.

YOUR ROUND 2: {bear_r2}
BULL'S ROUND 2: {bull_r2}

Provide FINAL position. If you've updated significantly, state it explicitly. 150 words max.

FINAL BEAR POSITION:
[clear stance]
CONFIDENCE (1-10): [N]
RECOMMENDED ACTION: [SHORT / AVOID / WAIT]"""


def _cosine_similarity(v1, v2):
    import numpy as np

    if v1 is None or v2 is None:
        return None
    norm = float(np.linalg.norm(v1) * np.linalg.norm(v2))
    if norm == 0:
        return None
    return float(np.dot(v1, v2) / norm)


def run_multi_round_debate(ticker, context_text):
    """3-round dialectic. Returns dict with rounds + convergence_score + verdict."""
    from datetime import datetime as _dt

    from shared import llm

    try:
        from shared import embeddings
    except ImportError:
        embeddings = None

    # Inject anchor date into context for all 3 rounds (Round 2/3 inherit via R1)
    today_str = _dt.now().strftime("%d %B %Y")
    today_iso = _dt.now().strftime("%Y-%m-%d")
    current_quarter = f"Q{((_dt.now().month - 1) // 3) + 1} {_dt.now().year}"
    next_quarter_year = _dt.now().year + (1 if _dt.now().month >= 10 else 0)
    next_quarter = f"Q{((_dt.now().month - 1) // 3 + 1) % 4 + 1} {next_quarter_year}"

    anchor_block = (
        f"\n=== ANCHOR DATE (CRITICAL) ===\n"
        f"TODAY IS {today_str} ({today_iso}). Current quarter is {current_quarter}.\n"
        f"- ALL forward-looking catalysts MUST be events AFTER {today_iso}.\n"
        f"  NEXT earnings for most companies = {next_quarter} or {current_quarter}.\n"
        f"- DO NOT cite past events (Q3 2024, FY2024, October 2024) as forward catalysts.\n"
        f"- DO NOT cite 'post-election' without specifying which election.\n"
        f"- If your training data is older than today, acknowledge it and reason from\n"
        f"  the structured context provided below.\n"
    )
    context_with_anchor = anchor_block + "\n" + context_text

    out = {"ticker": ticker.upper(), "rounds": []}

    # Round 1 — parallel
    log.info(f"debate {ticker} R1 start")
    r1_bull = llm.call(ROUND_1_BULL.format(ticker=ticker, context=context_with_anchor), tier="enrich", max_tokens=900)
    r1_bear = llm.call(ROUND_1_BEAR.format(ticker=ticker, context=context_with_anchor), tier="enrich", max_tokens=900)
    out["rounds"].append({"round": 1, "bull": r1_bull, "bear": r1_bear})

    # Round 2 — cross-challenge
    log.info(f"debate {ticker} R2 start")
    r2_bull = llm.call(ROUND_2_BULL.format(bear_r1=r1_bear), tier="enrich", max_tokens=700)
    r2_bear = llm.call(ROUND_2_BEAR.format(bull_r1=r1_bull), tier="enrich", max_tokens=700)
    out["rounds"].append({"round": 2, "bull": r2_bull, "bear": r2_bear})

    # Round 3 — final positions
    log.info(f"debate {ticker} R3 start")
    r3_bull = llm.call(ROUND_3_BULL.format(bull_r2=r2_bull, bear_r2=r2_bear), tier="enrich", max_tokens=500)
    r3_bear = llm.call(ROUND_3_BEAR.format(bear_r2=r2_bear, bull_r2=r2_bull), tier="enrich", max_tokens=500)
    out["rounds"].append({"round": 3, "bull": r3_bull, "bear": r3_bear})

    # Convergence on R3 final positions
    cs = None
    if embeddings is not None:
        try:
            emb_bull = embeddings.embed_text(r3_bull)
            emb_bear = embeddings.embed_text(r3_bear)
            cs = _cosine_similarity(emb_bull, emb_bear)
        except Exception as e:
            log.warning(f"convergence embedding failed: {e}")

    out["convergence_score"] = cs
    if cs is None:
        out["verdict"] = "UNKNOWN — embedding unavailable"
    elif cs > 0.7:
        out["verdict"] = "CONVERGED — high conviction signal"
    elif cs > 0.4:
        out["verdict"] = "MODERATE — partial agreement"
    else:
        out["verdict"] = "DIVERGED — complexity flag, deserves caution"

    return out


def format_debate_for_telegram(out, max_chunk=3500):
    """Format multi-round debate into Telegram chunks."""
    if "error" in out:
        return [f"Debate failed: {out['error']}"]
    chunks = []
    cs = out.get("convergence_score")
    verdict = out.get("verdict", "unknown")
    header = f"MULTI-ROUND DEBATE — {out['ticker']}"
    if cs is not None:
        header += f"\nConvergence: {cs:.2f}  → {verdict}"
    else:
        header += f"\n{verdict}"
    chunks.append(header)

    for r in out.get("rounds", []):
        rn = r["round"]
        bull = (r.get("bull") or "")[: max_chunk - 200]
        bear = (r.get("bear") or "")[: max_chunk - 200]
        chunks.append(f"━━━ ROUND {rn} • BULL ━━━\n\n{bull}")
        chunks.append(f"━━━ ROUND {rn} • BEAR ━━━\n\n{bear}")
    return chunks
