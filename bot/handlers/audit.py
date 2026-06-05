"""Handler `/audit` : surface decision_audit (per-decision copilot + counterfactual)
en compact Telegram.

Pattern : 1 commande -> dans le flow naturel quotidien -> friction zero ->
discipline d'auto-critique mecanisee. Cf [[niveau-2-adversary-and-proof]]
move #2 : miroir-qui-conteste tes decisions a posteriori.

Usage :
  /audit         -> derniers 7j
  /audit 14      -> derniers 14j
  /audit MU      -> filtre ticker
  /audit MU 30   -> filtre + window
"""

from __future__ import annotations

import json
import logging
import sqlite3

from shared import storage

log = logging.getLogger(__name__)


async def cmd_audit(update, ctx):  # noqa: ARG001
    """Surface per-decision audit (copilot + counterfactual) en compact Telegram."""
    parts = update.message.text.split()[1:]

    days = 7
    ticker: str | None = None
    for p in parts:
        if p.isdigit():
            days = int(p)
        elif p.isalpha() or "." in p or "_" in p:
            ticker = p.upper()

    # Import core logic from the script (avoid duplication).
    from scripts.decision_audit import (
        classify_decision,
        fetch_copilot_intervention,
        fetch_counterfactual,
        fetch_decisions,
    )

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        decisions = fetch_decisions(conn, days, ticker)
        if not decisions:
            await update.message.reply_text(
                f"AUDIT {days}j" + (f" ({ticker})" if ticker else "")
                + " : aucune decision materielle reelle dans la fenetre."
            )
            return

        rows = []
        for d in decisions:
            cop = fetch_copilot_intervention(conn, d["id"])
            cf = fetch_counterfactual(conn, d["id"])
            classification = classify_decision(cop, cf).split(" ")[0]
            rows.append((d, cop, cf, classification))
    finally:
        conn.close()

    # Aggregate classifications
    counts: dict[str, int] = {}
    n_copilot = 0
    n_cf = 0
    n_resolved = 0
    for _d, cop, cf, c in rows:
        counts[c] = counts.get(c, 0) + 1
        if cop:
            n_copilot += 1
        if cf:
            n_cf += 1
            if cf.get("resolutions"):
                n_resolved += 1

    header = f"AUDIT {days}j" + (f" ({ticker})" if ticker else "") + f" — {len(rows)} decisions"
    lines = [header, ""]

    # Classification summary
    lines.append("Classification :")
    important_first = ("PUSHED_THROUGH", "BLIND_SPOT", "COPILOT_WRONG", "OK", "PENDING")
    for c in important_first:
        if c in counts:
            marker = ""
            if c == "PUSHED_THROUGH":
                marker = " ⚠️"
            elif c == "BLIND_SPOT":
                marker = " ❓"
            elif c == "COPILOT_WRONG":
                marker = " 🔧"
            lines.append(f"  {c}: {counts[c]}{marker}")
    lines.append("")

    # Coverage
    lines.append(f"Coverage : copilot {n_copilot}/{len(rows)} | cf {n_cf}/{len(rows)} "
                 f"| resolved {n_resolved}/{n_cf}")
    lines.append("")

    # Detail per decision (truncated to fit Telegram 4096 char limit)
    lines.append("Decisions (recent first) :")
    MAX_DETAIL = 15
    for d, cop, cf, c in rows[:MAX_DETAIL]:
        # 1 ligne par decision : id, ticker, type, date, verdict copilot, classif
        cop_v = cop["verdict"] if cop else "no-cp"
        cop_p = f"{cop['pressure_score']}" if cop and cop.get("pressure_score") else "-"
        cf_state = "no-cf"
        if cf:
            if cf.get("resolutions"):
                # Verdict de la resolution la plus longue
                last_res = cf["resolutions"][-1]
                v = last_res["verdict"]
                cf_state = f"J+{last_res['horizon']}:{v.replace('decision_', '')}"
            else:
                cf_state = f"cf:{cf['branch']}"

        # Bias flagging if any
        bias_marker = ""
        if cf and cf.get("biases"):
            try:
                bl = json.loads(cf["biases"])
                if bl and any("winner" in b for b in bl):
                    bias_marker = " 💸"  # winner-sell suspect
            except Exception:
                pass

        date_short = d["created_at"][:10]
        lines.append(
            f"#{d['id']} {d['ticker']:<10} {d['decision_type']:<13} {date_short} "
            f"cp:{cop_v}/{cop_p} {cf_state} [{c}]{bias_marker}"
        )

    if len(rows) > MAX_DETAIL:
        lines.append(f"... +{len(rows) - MAX_DETAIL} autres (cf scripts/decision_audit.py pour full)")

    msg = "\n".join(lines)
    # Telegram 4096 char limit safety
    if len(msg) > 3900:
        msg = msg[:3850] + "\n... [truncated]"

    await update.message.reply_text(msg)
