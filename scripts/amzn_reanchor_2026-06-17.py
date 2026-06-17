"""Re-anchor AMZN thesis targets — méthode #135 (17/06/2026).

## Context

Monitor `stale_target` (commit 5f5c5a8) avait marqué AMZN dying à edge_partial
+0.3%. Méthode #135 3 colonnes appliquée :

- Colonne 1 (Instrument) : current px $246, partial $246.78 (essentiellement
  hit), full $268.74 (+9.2%), stop $172.82 (-29.7%), c4, value €2422
- Colonne 2 (Ancre externe live, Bigdata.com) : Q1 2026 earnings massive,
  AWS accélère
- Colonne 3 (Ressenti, user) : validé re-anchor higher

## Evidence Bigdata.com (Q1 2026 - 29 avril 2026)

- Revenue $181.5B (+17% YoY, +15% FX-neutral)
- AWS $37.6B (+28% YoY, **fastest growth in 15 quarters**)
- AWS run rate $150B annualized / Q1 OI $14.2B (margin ~38%)
- AWS AI revenue run rate $15B (vs $58M when AWS was 3y old = 256× faster)
- Trainium chip rev +40% QoQ, **$20B+ annual run rate**
- New AI clients : OpenAI, Anthropic, Meta, NVIDIA, Uber, US Bank, etc.
- Bedrock customer spend +170% QoQ
- North America OI margin 7.9% / International 3.6%
- Q2 guidance : $194-199B sales, $20-24B OI

## Verdict

Tous les 5 invalidation_triggers SAFE avec large marge :
1. AWS YoY <15% × 2Q → 28% actuel (SAFE)
2. AWS GM <55% → ~65%+ gross, OI margin 38% (SAFE)
3. Retail OI <5% × 2Q → NA 7.9% (SAFE)
4. Capex hyperscaler pause >2Q → CapEx $43.2B Q1 UP (SAFE)
5. Kuiper over-run → pas de signal 10-Q (SAFE)

Targets actuels obsolètes vs trajectoire AWS. Re-anchor reflète :
- AWS accel structurelle (+28% > 15-20% attendu prior)
- AI run rate composant 256× plus rapide qu'historique
- Trainium émerge en alternative Nvidia crédible
- Customer wins majeurs (OpenAI = stratégique)

## Cure

- target_partial : $246.78 → **$290** (+17.9% from current $246)
- target_full : $268.74 → **$330** (+34.1% from current)
- conviction : c4 maintenu (possible c5 si Q2 print encore fort)
- stop : $172.82 maintenu (-29.7%)
- Triggers : aucun rewrite (tous data-backed)

## Idempotence

Le script vérifie target_partial actuel avant UPDATE. Si déjà $290, skip.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "bot.db"

NEW_TARGET_PARTIAL = 290.0
NEW_TARGET_FULL = 330.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        return 1

    cx = sqlite3.connect(DB)
    row = cx.execute(
        "SELECT id, target_partial, target_full FROM theses WHERE ticker='AMZN' AND status='active'"
    ).fetchone()
    if not row:
        print("ERROR: AMZN active thesis not found", file=sys.stderr)
        return 1

    thesis_id, current_partial, current_full = row

    if abs(current_partial - NEW_TARGET_PARTIAL) < 0.01 and abs(current_full - NEW_TARGET_FULL) < 0.01:
        print(
            f"AMZN thesis #{thesis_id} déjà re-anchored. Skip idempotent.\n"
            f"  Current: partial={current_partial}, full={current_full}"
        )
        return 0

    print("═ AMZN re-anchor (méthode #135) ═\n")
    print(f"AVANT (thesis #{thesis_id}):")
    print(f"  target_partial: ${current_partial}")
    print(f"  target_full   : ${current_full}\n")
    print("APRÈS:")
    print(f"  target_partial: ${NEW_TARGET_PARTIAL}")
    print(f"  target_full   : ${NEW_TARGET_FULL}\n")

    if args.apply:
        cx.execute(
            "UPDATE theses SET target_partial = ?, target_full = ? WHERE id = ?",
            (NEW_TARGET_PARTIAL, NEW_TARGET_FULL, thesis_id),
        )
        cx.commit()
        print("→ APPLIED")
    else:
        print("(dry-run, pass --apply pour modifier DB)")

    cx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
