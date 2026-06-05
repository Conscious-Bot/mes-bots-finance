"""Per-decision audit : qu'est-ce que j'ai fait, et c'etait bon ?

Vue timeline des decisions reelles + copilot intervention (verdict + pressure) +
contrefactuel resolu (J+30/J+60/J+90 vs hold). Surface les cas a haute valeur
d'apprentissage :

  - PUSHED_THROUGH : copilot a warn (PRESSURE/STRONG_OPPOSE), user a override,
    le counterfactual dit que c'etait une mauvaise decision -> user ignore valid
    pushback (a corriger forward)
  - COPILOT_WRONG : copilot a warn, user override, counterfactual benefice -> le
    copilot a cri au loup, calibrer
  - BLIND_SPOT : pas de copilot warn, counterfactual harmful -> trou de detection
    (a investiguer : quel pattern aurait du fire ?)
  - VINDICATED : copilot warn, user listened (no decision_id linked), pas de cf
    a auditer -> bonne discipline

Cf [[niveau-2-adversary-and-proof]] : c'est le move #2 contrefactuel decisions
qui est le pick utilisateur pour passer de miroir-qui-decrit a adversaire-qui-
conteste + preuve-d-edge.

Usage :
  python -m scripts.decision_audit
  python -m scripts.decision_audit --days 30
  python -m scripts.decision_audit --ticker NVDA
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("decision_audit")

MATERIAL_TYPES = ("entry", "scale_in", "partial_exit", "full_exit", "override")


def fetch_decisions(
    conn: sqlite3.Connection,
    days: int,
    ticker: str | None,
) -> list[dict]:
    """Decisions reelles materielles dans la fenetre, filter TEST + VOIDED."""
    extra = ""
    params: list = [f"-{days} days"]
    if ticker:
        extra = " AND ticker = ?"
        params.append(ticker)

    placeholders = ",".join("?" * len(MATERIAL_TYPES))
    rows = conn.execute(
        f"""
        SELECT id, ticker, decision_type, created_at, reasoning,
               thesis_id, price_at_decision
        FROM decisions
        WHERE created_at >= datetime('now', ?)
          AND decision_type IN ({placeholders})
          AND ticker NOT LIKE 'TEST_%' AND ticker NOT LIKE 'test%'
          AND (reasoning IS NULL OR reasoning NOT LIKE '[VOIDED %')
          {extra}
        ORDER BY created_at DESC
        """,
        (*params, *MATERIAL_TYPES),
    ).fetchall()
    return [{
        "id": r[0], "ticker": r[1], "decision_type": r[2],
        "created_at": r[3], "reasoning": r[4],
        "thesis_id": r[5], "price": r[6],
    } for r in rows]


def fetch_copilot_intervention(conn: sqlite3.Connection, decision_id: int) -> dict | None:
    """L'intervention copilot liee a une decision (s'il y en a eu une)."""
    row = conn.execute(
        """
        SELECT verdict, pressure_score, ancrage, brief, biases_active_json,
               cost_usd
        FROM bot_copilot_interventions
        WHERE decision_id = ?
        LIMIT 1
        """,
        (decision_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "verdict": row[0], "pressure_score": row[1], "ancrage": row[2],
        "brief": row[3], "biases": row[4], "cost_usd": row[5],
    }


def fetch_counterfactual(conn: sqlite3.Connection, decision_id: int) -> dict | None:
    """Ancre + resolution(s) du counterfactual lie a la decision."""
    dcf_row = conn.execute(
        """
        SELECT dcf.id, dcf.counterfactual_branch, dcf.anchor_price_native,
               dcf.bias_hypothesis_json
        FROM decision_counterfactual dcf
        WHERE dcf.decision_id = ?
        LIMIT 1
        """,
        (decision_id,),
    ).fetchone()
    if not dcf_row:
        return None
    dcf_id = dcf_row[0]

    # Resolutions (peut etre 0, 1, 2, ou 3 selon horizons mature)
    resolutions = conn.execute(
        """
        SELECT horizon_days, ROUND(delta_eur, 2), ROUND(delta_pct, 1), verdict
        FROM counterfactual_resolution
        WHERE decision_counterfactual_id = ?
        ORDER BY horizon_days
        """,
        (dcf_id,),
    ).fetchall()

    return {
        "dcf_id": dcf_id,
        "branch": dcf_row[1],
        "anchor_price": dcf_row[2],
        "biases": dcf_row[3],
        "resolutions": [
            {"horizon": r[0], "delta_eur": r[1], "delta_pct": r[2], "verdict": r[3]}
            for r in resolutions
        ],
    }


def classify_decision(copilot: dict | None, counterfactual: dict | None) -> str:
    """Categorise le case d'apprentissage pour highlighting."""
    warned = (
        copilot
        and copilot.get("verdict") in ("PRESSURE", "STRONG_OPPOSE")
    )
    has_resolution = (
        counterfactual
        and len(counterfactual.get("resolutions", [])) > 0
    )

    if not has_resolution:
        return "PENDING (counterfactual pas encore resolu)"

    # Take the longest-horizon resolution as the verdict
    res = counterfactual["resolutions"][-1]
    harmful = res["verdict"] == "decision_harmful"

    if warned and harmful:
        return "PUSHED_THROUGH (copilot warn ignore, decision harmful) -- A CORRIGER"
    if warned and not harmful:
        return "COPILOT_WRONG (copilot warn, decision OK) -- copilot a calibrer"
    if not warned and harmful:
        return "BLIND_SPOT (pas de warn, mais harmful) -- A INVESTIGUER"
    return "OK (pas de warn, decision OK)"


def print_decision(d: dict, copilot: dict | None, cf: dict | None) -> None:
    classification = classify_decision(copilot, cf)
    print(f"\n━━ #{d['id']} {d['ticker']} {d['decision_type']} ━━ {d['created_at'][:16]} ━━")
    print(f"  Classification : {classification}")
    if d["reasoning"]:
        reason = d["reasoning"][:150]
        print(f"  Reasoning : {reason}{'...' if len(d['reasoning']) > 150 else ''}")
    if d["price"]:
        print(f"  Price @ decision : {d['price']}")

    if copilot:
        v = copilot["verdict"] or "?"
        p = copilot["pressure_score"] or 0
        print(f"  Copilot : {v} pressure={p}/100")
        if copilot["brief"]:
            brief = copilot["brief"][:200]
            print(f"    brief : {brief}{'...' if len(copilot['brief']) > 200 else ''}")
        if copilot["biases"]:
            try:
                bl = json.loads(copilot["biases"])
                if bl:
                    print(f"    biases flagged : {bl}")
            except Exception:
                pass
    else:
        print("  Copilot : (pas d'intervention enregistree)")

    if cf:
        print(f"  Counterfactual branch : {cf['branch']}")
        if cf["resolutions"]:
            for r in cf["resolutions"]:
                v = r["verdict"]
                marker = "✗" if v == "decision_harmful" else ("✓" if v == "decision_beneficial" else "○")
                print(f"    {marker} J+{r['horizon']:>2}d : {r['delta_eur']:+.2f}EUR "
                      f"({r['delta_pct']:+.1f}%) -> {v}")
        else:
            print("    (pas encore resolu, mature attendu a J+30)")
        if cf["biases"]:
            try:
                bl = json.loads(cf["biases"])
                if bl:
                    print(f"  Biases hypothese (anchor) : {bl}")
            except Exception:
                pass
    else:
        print("  Counterfactual : (pas d'ancre enregistree) /!\\")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=14,
                        help="Fenetre de decisions a auditer (default 14j).")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Restrict a un ticker.")
    args = parser.parse_args()

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        decisions = fetch_decisions(conn, args.days, args.ticker)
        if not decisions:
            print(f"Aucune decision reelle dans la fenetre {args.days}j"
                  + (f" pour {args.ticker}" if args.ticker else "") + ".")
            return

        print("\n" + "=" * 80)
        print(f"DECISION AUDIT — {len(decisions)} decisions reelles "
              f"sur {args.days}j"
              + (f" (ticker={args.ticker})" if args.ticker else ""))
        print("=" * 80)

        # Pour chaque decision, fetch copilot + counterfactual
        rows = []
        for d in decisions:
            copilot = fetch_copilot_intervention(conn, d["id"])
            cf = fetch_counterfactual(conn, d["id"])
            print_decision(d, copilot, cf)
            rows.append((d, copilot, cf))

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        counts: dict[str, int] = {}
        for _d, copilot, cf in rows:
            c = classify_decision(copilot, cf).split(" ")[0]
            counts[c] = counts.get(c, 0) + 1
        for category, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {category:<20} : {n}")

        n_with_copilot = sum(1 for _d, c, _cf in rows if c)
        n_with_cf = sum(1 for _d, _c, cf in rows if cf)
        n_with_resolution = sum(
            1 for _d, _c, cf in rows
            if cf and cf.get("resolutions")
        )
        print()
        print(f"Couverture copilot : {n_with_copilot}/{len(rows)} decisions")
        print(f"Couverture counterfactual : {n_with_cf}/{len(rows)} decisions")
        print(f"Resolu (J+N mature) : {n_with_resolution}/{n_with_cf}")
        print("=" * 80)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
