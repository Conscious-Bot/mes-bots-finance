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

Format readable (refactor 05/06 soir) : groupe par date, verdicts en mots
clairs (Stop/Pression/OK/—), branches cf en francais (vs vendre / vs garder),
visuels alignes (⛔/⚠️/✓/·).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict

from shared import storage

log = logging.getLogger(__name__)

# Mappings verdict -> visuel + label humain
_COP_VERDICT_DISPLAY: dict[str, tuple[str, str]] = {
    "STRONG_OPPOSE": ("⛔", "Stop"),
    "PRESSURE": ("⚠️", "Pression"),
    "PROCEED": ("✓", "OK"),
}

# Branches counterfactuelles -> francais
_CF_BRANCH_DISPLAY: dict[str, str] = {
    "hold": "vs garder",
    "would_have_sold": "vs vendre",
    "rotate_to": "vs roter",
}


def _format_decision_line(d: dict, cop: dict | None, cf: dict | None) -> str:
    """1 ligne Telegram aligned for a single decision."""
    # Verdict copilot
    if cop and cop.get("verdict") in _COP_VERDICT_DISPLAY:
        icon, label = _COP_VERDICT_DISPLAY[cop["verdict"]]
        score = cop.get("pressure_score") or 0
        cop_part = f"{icon} {label:<8}/{score:<2}"
    else:
        cop_part = "·  —       /-- "

    # Counterfactual : si resolu, montre le verdict realise ; sinon la branche pending
    if cf and cf.get("resolutions"):
        last_res = cf["resolutions"][-1]
        v = last_res["verdict"].replace("decision_", "")
        # Translate v : harmful / beneficial / neutral
        v_fr = {"harmful": "❌perte", "beneficial": "✅gain", "neutral": "○neutre"}.get(v, v)
        cf_part = f"J+{last_res['horizon']}d {v_fr}"
    elif cf:
        cf_part = _CF_BRANCH_DISPLAY.get(cf["branch"], cf["branch"])
    else:
        cf_part = "(no cf)"

    # Marker biais winner-sell suspect
    bias_marker = ""
    if cf and cf.get("biases"):
        try:
            bl = json.loads(cf["biases"])
            if bl and any("winner" in b for b in bl):
                bias_marker = " 💸"
        except Exception:
            pass

    return (
        f"  {d['ticker']:<10} {d['decision_type']:<13} "
        f"{cop_part} {cf_part}{bias_marker}"
    )


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
                f"🔍 AUDIT {days}j" + (f" ({ticker})" if ticker else "")
                + "\n\nAucune décision matérielle réelle sur la fenêtre."
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

    # Aggregate classifications + coverage
    counts: dict[str, int] = {}
    n_copilot = 0
    n_cf = 0
    n_resolved = 0
    for _d, cop, cf, c in rows:
        counts[c] = counts.get(c, 0) + 1
        if cop and cop.get("verdict"):
            n_copilot += 1
        if cf:
            n_cf += 1
            if cf.get("resolutions"):
                n_resolved += 1

    # Header
    title = f"🔍 AUDIT {days}j" + (f" — {ticker}" if ticker else "")
    n = len(rows)
    lines = [f"{title} — {n} décision{'s' if n > 1 else ''}", ""]

    # Status : pour l'instant majoritairement PENDING
    if counts.get("PENDING") == n:
        lines.append("État : aucune mature (premiers verdicts vers fin juin)")
    else:
        # Classification avec markers visuels uniquement pour les categories "learning"
        bits = []
        if counts.get("PUSHED_THROUGH"):
            bits.append(f"⚠️ {counts['PUSHED_THROUGH']} pushed-through")
        if counts.get("BLIND_SPOT"):
            bits.append(f"❓ {counts['BLIND_SPOT']} blind-spot")
        if counts.get("COPILOT_WRONG"):
            bits.append(f"🔧 {counts['COPILOT_WRONG']} copilot-wrong")
        if counts.get("OK"):
            bits.append(f"✓ {counts['OK']} ok")
        if counts.get("PENDING"):
            bits.append(f"⏳ {counts['PENDING']} pending")
        if bits:
            lines.append("État : " + " · ".join(bits))

    lines.append(f"Couverture : copilot {n_copilot}/{n} · cf {n_cf}/{n} · résolu {n_resolved}/{n_cf if n_cf else 0}")
    lines.append("")

    # Group par date
    by_date: dict[str, list] = defaultdict(list)
    for d, cop, cf, c in rows:
        date_key = d["created_at"][:10]
        by_date[date_key].append((d, cop, cf, c))

    # Sorted dates DESC (récent en premier)
    sorted_dates = sorted(by_date.keys(), reverse=True)

    MAX_TOTAL = 18  # cap pour Telegram limit
    n_shown = 0
    for date_key in sorted_dates:
        decisions_day = by_date[date_key]
        if n_shown >= MAX_TOTAL:
            break

        # Format date : 2026-06-03 -> 03/06
        try:
            _yyyy, mm, dd = date_key.split("-")
            date_label = f"{dd}/{mm}"
        except Exception:
            date_label = date_key

        lines.append(f"━ {date_label} ({len(decisions_day)})")
        for d, cop, cf, _c in decisions_day:
            if n_shown >= MAX_TOTAL:
                break
            lines.append(_format_decision_line(d, cop, cf))
            n_shown += 1
        lines.append("")

    if n > MAX_TOTAL:
        lines.append(f"… +{n - MAX_TOTAL} autres (cf `python -m scripts.decision_audit` pour full)")

    # Légende compacte si pertinent
    if any(cop and cop.get("verdict") for _d, cop, _cf, _c in rows):
        lines.append("")
        lines.append("Légende : ⛔ Stop · ⚠️ Pression · ✓ OK · 💸 winner-sell suspect")

    msg = "\n".join(lines).rstrip()
    if len(msg) > 3900:
        msg = msg[:3850] + "\n…[truncated]"

    await update.message.reply_text(msg)
