"""Phase 1 quality test for adversarial co-pilot on REAL ticker from DB.

Usage : python3 scripts/copilot_test.py <TICKER> [scale_in|partial_exit|full_exit]

Pulls a real active thesis from the DB, assembles fresh context (signals last 30d,
past user decisions, bias patterns), runs the co-pilot LLM call, prints the JSON
output for evaluation against the quality bar :
- Do specific_arguments cite real evidence_ids ?
- Is bear_case_oneliner SPECIFIC (numbers, signal refs) not GENERIC ?
- Is pressure_score calibrated to actual evidence weight ?
- If no real opposing evidence : does it correctly output PROCEED + 0 arguments ?
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fetch_thesis(con, ticker: str) -> dict | None:
    row = con.execute("SELECT * FROM theses WHERE ticker=? AND status='active' ORDER BY rowid DESC LIMIT 1", (ticker,)).fetchone()
    if not row:
        return None
    return dict(row)


def _fetch_recent_signals(con, ticker: str) -> list[dict]:
    """Pull signals : DIRECT (on this ticker) + ADJACENT (other tickers in same sector).
    Adjacent signals are the moat — they inform the thesis even when not on the target ticker."""
    # 1. Direct signals on this ticker
    direct = con.execute(
        """SELECT s.id, s.timestamp, s.title, s.summary, s.sentiment, s.score,
                  s.entities, src.credibility AS source_credibility
           FROM signals s
           LEFT JOIN sources src ON src.id = s.source_id
           WHERE s.timestamp > datetime('now', '-30 day')
             AND (s.entities LIKE ? OR s.title LIKE ? OR s.content LIKE ?)
           ORDER BY s.timestamp DESC LIMIT 12""",
        (f"%{ticker}%", f"%{ticker}%", f"%{ticker}%"),
    ).fetchall()

    # 2. Adjacent signals : same sector tickers
    from shared import taxonomy  # source unique catégorisation (cure 5 sources → 1, 26/06/2026)

    try:
        sector = taxonomy.sector_highlevel(ticker)
    except taxonomy.TaxonomyError:
        sector = None
    adjacent_rows = []
    if sector:
        same_sector_tks = taxonomy.same_sector_tickers(ticker)
        if same_sector_tks:
            placeholders = " OR ".join(["s.entities LIKE ?" for _ in same_sector_tks])
            params = [f"%{tk}%" for tk in same_sector_tks]
            adjacent_rows = con.execute(
                f"""SELECT s.id, s.timestamp, s.title, s.summary, s.sentiment, s.score,
                           s.entities, src.credibility AS source_credibility
                    FROM signals s
                    LEFT JOIN sources src ON src.id = s.source_id
                    WHERE s.timestamp > datetime('now', '-30 day')
                      AND ({placeholders})
                    ORDER BY s.timestamp DESC LIMIT 10""",
                params,
            ).fetchall()

    # signals.score is on 1-8 native scale (intelligence/materiality.py).
    # Keep score >= 4 = "material enough to consider" (drops ~58% of noise).
    out = []
    for r in direct:
        d = dict(r)
        d["materiality"] = d.get("score") or 0  # native 1-8 scale, keep as int
        d["scope"] = "direct"
        out.append(d)
    for r in adjacent_rows:
        d = dict(r)
        d["materiality"] = d.get("score") or 0
        d["scope"] = f"adjacent (sector: {sector})"
        out.append(d)

    out = [s for s in out if s.get("materiality", 0) >= 4]
    out.sort(key=lambda s: (s["scope"] != "direct", s["timestamp"]), reverse=False)
    out.reverse()
    return out[:10]


def _fetch_past_decisions(con, ticker: str, decision_type: str) -> list[dict]:
    # Past decisions on the SAME ticker or same type with resolved outcomes
    rows = con.execute(
        """SELECT id, created_at, ticker, decision_type, direction, reasoning,
                  resolved_30d_at, return_30d_pct, bias_tags, thesis_relative_30d
           FROM decisions
           WHERE (ticker=? OR decision_type=?) AND resolved_30d_at IS NOT NULL
           ORDER BY created_at DESC LIMIT 10""",
        (ticker, decision_type),
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_bias_patterns(con) -> list[dict]:
    rows = con.execute(
        """SELECT name, description, n_samples, avg_outcome, success_rate
           FROM patterns WHERE is_active=1 AND n_samples >= 3
           ORDER BY n_samples DESC LIMIT 5"""
    ).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage : python3 scripts/copilot_test.py <TICKER> [scale_in|partial_exit|full_exit]")
        return 1

    ticker = sys.argv[1].upper()
    decision_type = sys.argv[2] if len(sys.argv) > 2 else "partial_exit"

    con = sqlite3.connect("file:data/bot.db?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    thesis = _fetch_thesis(con, ticker)
    if not thesis:
        print(f"No active thesis on {ticker}. Available active theses :")
        for r in con.execute("SELECT ticker, conviction FROM theses WHERE status='active' ORDER BY conviction DESC LIMIT 15"):
            print(f"  {r[0]:12s} c{r[1]}")
        return 2

    print(f"\n========== CONTEXT ASSEMBLED FOR {ticker} ({decision_type}) ==========\n")
    print(f"Thesis : c{thesis['conviction']} {thesis['direction']} | entry ${thesis['entry_price']} | "
          f"target ${thesis['target_full']} | stop ${thesis['stop_price']}")
    print(f"Last price : ${thesis.get('last_price', '?')}")
    print(f"Pre-mortem on file : {'YES' if thesis.get('pre_mortem') else 'NO'}")

    signals = _fetch_recent_signals(con, ticker)
    print(f"\nRecent signals (last 30d, materiality >= 0.40) : {len(signals)} found")
    for s in signals[:3]:
        print(f"  - {s['timestamp'][:10]} | mat {s['materiality']:.2f} | {(s.get('title') or s.get('summary') or '')[:90]}")

    past_decisions = _fetch_past_decisions(con, ticker, decision_type)
    print(f"\nPast similar decisions (same ticker OR same type, resolved) : {len(past_decisions)} found")
    for d in past_decisions[:3]:
        print(f"  - {d['created_at'][:10]} | {d['decision_type']} {d['ticker']} | "
              f"return_30d {d.get('return_30d_pct', '?')}% | biases {d.get('bias_tags', '[]')[:40]}")

    biases = _fetch_bias_patterns(con)
    print(f"\nActive bias patterns (in DB) : {len(biases)} found")
    for b in biases:
        print(f"  - {b['name']} (n={b['n_samples']}, avg_outcome {b.get('avg_outcome', 0):+.1f}%)")

    intent = {
        "decision_type": decision_type,
        "reasoning": "Test invocation — investor wants to test the co-pilot quality bar",
        "confidence_pre": 4,
        "current_price": thesis.get("last_price") or thesis.get("entry_price") or 0,
    }

    from intelligence import decision_copilot as cp

    # Dry-run mode : print assembled prompt, don't call LLM
    if "--dry-run" in sys.argv or not __import__("os").environ.get("ANTHROPIC_API_KEY"):
        print("\n========== DRY-RUN : assembled prompt (no LLM call) ==========\n")
        ctx = cp.assemble_context(intent, thesis, signals, past_decisions, biases)
        full_prompt = cp.PROMPT.format(**ctx)
        print(full_prompt)
        print("\n========== END PROMPT — LLM would receive this ==========")
        print("To call LLM : export ANTHROPIC_API_KEY=... then re-run without --dry-run")
        return 0

    print("\n========== INVOKING CLAUDE (synthesize tier) ==========\n")
    result = cp.run_copilot(intent, thesis, signals, past_decisions, biases)
    if result is None:
        print("ERROR : copilot returned None (see logs)")
        return 3

    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\n========== QUALITY BAR EVAL ==========\n")
    print(f"Verdict : {result.get('verdict')}")
    print(f"Pressure score : {result.get('pressure_score')}")
    print(f"Biases flagged : {result.get('biases_active', [])}")
    print(f"\nAncrage : {result.get('ancrage', '?')}")
    print(f"\nBrief :\n{result.get('brief', '?')}")

    # Quality red flags
    ancrage = result.get("ancrage", "") or ""
    brief = result.get("brief", "") or ""
    PLATITUDES = ["reconsidere", "attention aux biais", "diversifie", "pense au risque", "tiens ton plan", "reste discipline"]
    found_plat = [p for p in PLATITUDES if p in brief.lower()]
    if found_plat:
        print(f"\n⚠️ PLATITUDE detectee dans brief : {found_plat}")
    if result.get("pressure_score", 0) > 30 and not any(c.isdigit() for c in brief):
        print("⚠️ pressure_score elevee mais brief sans aucun nombre concret — risque platitude")
    if ancrage and "signal_" not in ancrage and not any(c.isdigit() for c in ancrage):
        print("⚠️ ancrage sans citation signal_id ni nombre — manque de specificite")

    return 0


if __name__ == "__main__":
    sys.exit(main())
