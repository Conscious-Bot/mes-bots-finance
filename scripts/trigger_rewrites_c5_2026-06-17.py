"""Trigger rewrites batch c5 — méthode #135 systematic test 2026-06-17.

## Contexte

User a demandé "test triggers one by one" pour toutes les positions, sequential
by conviction décroissante. C5 batch fait : 7 tickers × 3-4 triggers chacun =
23 triggers fact-checkés via Bigdata.com (~22 query units consommés).

**Résultat global** : 0/23 fired. **Thèses c5 toutes INTACTES** sur le
cycle bull actuel (cohérent avec memory `presage_biais_1_only` doctrine
discipline-mécanisée).

## Rewrites (6 triggers)

Motivations : trigger wording obsolète, metric discontinued, ou criteria
flou. Tous rewrites évitent codes "S{N}" pour empêcher faux positifs
cross-ref (cf commit 05c8d22 mécanisme + bf2df8a fix doctrine gate).

### ASML.AS #1 — metric discontinued

AVANT : "Bookings <€35B 2 Q consec."

APRÈS : "Annual backlog <€35B (next disclosure Q4 2026/FY annual report) OR
net sales 2 Q consécutifs <€7B (vs Q1 2026 €8.8B = -20% floor). NOTE :
quarterly bookings metric discontinued Jan 2026, mesures alternatives sur
annuel backlog ou sales trajectoire."

Evidence : Morningstar 15/04/2026 — ASML stopped quarterly bookings reporting.
Q1 2026 sales €8.8B above consensus €8.69B, backlog $46.47B end-2025.

### SNPS #1 — event résolu favorablement

AVANT : "Ansys merger blocked antitrust."

APRÈS : "Ansys intégration échec : synergies cumulées year-1 (FY26) < $200M
(vs guidance accélérée $400M sooner than year-3) OR operating margin
expansion FY26 < 200bps (vs +300bps guidance) OR Ansys segment revenue
Q3-Q4 < $1.8B/quarter. Note : merger Ansys completed favorably 17 juillet
2025, risk reversé sur exécution."

Evidence : SNPS Q2 2026 10-Q + earnings call — merger completed July 2025,
$400M synergies accelerated, +300bps margin expansion.

### TSM #2 — criteria flou

AVANT : "Samsung 2nm ramp succeeds significantly."

APRÈS : "Samsung foundry segment revenue >$5B/quarter sur 2 Q consec (vs
~$3B/Q current) OR ≥3 design wins externes annoncés publiquement hyperscaler
(MSFT/GOOGL/AMZN/META) / Nvidia / AMD / Apple sur 12 mois glissants sur
process 2nm = signal réel d'érosion TSMC monopole leading-edge."

Evidence : Samsung Q1 2026 — 2nm mass production starting H2 2026, Tesla
landmark deal, active discussions US/China customers.

### TSM #3 — criteria flou

AVANT : "Intel 18A succès >expected."

APRÈS : "Intel Foundry external revenue >$5B/Q sur 2 Q consec (vs ~$1-2B/Q
current) OR ≥3 hyperscaler / NVDA / AMD / AAPL design wins externes annoncés
publiquement sur Intel 14A/18A sur 12 mois glissants = signal réel d'érosion
TSMC monopole leading-edge (vs internal Intel products only)."

Evidence : Intel 18A in volume production (Panther Lake), 200 design wins
inc. internal, yields +7%/month, customers Intel 14A decisions H2 2026.

### CCJ #1 — threshold trop bas

AVANT : "Production cost > $40/lb sur 2 quarters (compression margin
structurelle)"

APRÈS : "AISC > $45 USD/lb OR C1 cash cost > $30/lb sur 2 quarters consec
(threshold actuel uranium long-term ~$91.50, ceiling escalated $160 — $45
AISC = compression margin réelle, vs $40 trigger original trop bas)."

Evidence : Cameco Q1 2026 — uranium long-term price $91.50, 70% market
paying >$100 already, cost increases minor 2026.

### CCJ #2 — binary trigger flou

AVANT : "Kazatomprom annonce return to full production (Russia-Kazakhstan
deal qui inonde marche)"

APRÈS : "Kazatomprom guidance >28,000 tons annual production OR
Russia-Kazakhstan deal allowing >35,000 tons combined output annoncé
publiquement = inonde marché. Baseline 2026 : KAP voluntary cut 25-26.5kt
(Bourse Direct 16/06/2026), value-over-volume strategy maintenue, 130Mlbs
removed 2017-2025. Opposé de trigger actuellement."

Evidence : Kazatomprom Q4 2025 earnings + Bourse Direct 16/06/2026 —
voluntary cut 25-26.5kt vs initial 27-29kt guidance.

## Triggers gardés tels quels (suffisamment spécifiques)

- ASML #2, #3
- SNPS #2, #3
- TSM #1 (GM <50% strong measurable)
- CCJ #3, #4
- SPCX #1, #2, #3, #4 (all binary events / measurable)
- 4063.T #1, #2, #3 (all measurable)
- 7011.T #1, #2, #3 (all measurable)

## Idempotence

Script vérifie wording actuel avant UPDATE. Skip si déjà rewritten.

## Usage

    python3 scripts/trigger_rewrites_c5_2026-06-17.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "bot.db"

REWRITES = {
    "ASML.AS": {
        0: {
            "hint": "Bookings <€35B 2 Q consec",
            "new": (
                "Annual backlog <€35B (next disclosure Q4 2026/FY annual report) OR net sales "
                "2 Q consécutifs <€7B (vs Q1 2026 €8.8B = -20% floor). NOTE : quarterly bookings "
                "metric discontinued Jan 2026, mesures alternatives sur annuel backlog ou "
                "sales trajectoire."
            ),
        },
    },
    "SNPS": {
        0: {
            "hint": "Ansys merger blocked antitrust",
            "new": (
                "Ansys intégration échec : synergies cumulées year-1 (FY26) < $200M (vs guidance "
                "accélérée $400M sooner than year-3) OR operating margin expansion FY26 < 200bps "
                "(vs +300bps guidance) OR Ansys segment revenue Q3-Q4 < $1.8B/quarter. Note : "
                "merger Ansys completed favorably 17 juillet 2025, risk reversé sur exécution."
            ),
        },
    },
    "TSM": {
        1: {
            "hint": "Samsung 2nm ramp succeeds significantly",
            "new": (
                "Samsung foundry segment revenue >$5B/quarter sur 2 Q consec (vs ~$3B/Q "
                "current) OR ≥3 design wins externes annoncés publiquement hyperscaler "
                "(MSFT/GOOGL/AMZN/META) / Nvidia / AMD / Apple sur 12 mois glissants sur "
                "process 2nm = signal réel d'érosion TSMC monopole leading-edge."
            ),
        },
        2: {
            "hint": "Intel 18A succès >expected",
            "new": (
                "Intel Foundry external revenue >$5B/Q sur 2 Q consec (vs ~$1-2B/Q current) "
                "OR ≥3 hyperscaler / NVDA / AMD / AAPL design wins externes annoncés "
                "publiquement sur Intel 14A/18A sur 12 mois glissants = signal réel "
                "d'érosion TSMC monopole leading-edge (vs internal Intel products only)."
            ),
        },
    },
    "CCJ": {
        0: {
            "hint": "Production cost > $40/lb sur 2 quarters",
            "new": (
                "AISC > $45 USD/lb OR C1 cash cost > $30/lb sur 2 quarters consec "
                "(threshold actuel uranium long-term ~$91.50, ceiling escalated $160 — "
                "$45 AISC = compression margin réelle, vs $40 trigger original trop bas)."
            ),
        },
        1: {
            "hint": "Kazatomprom annonce return to full production",
            "new": (
                "Kazatomprom guidance >28,000 tons annual production OR Russia-Kazakhstan deal "
                "allowing >35,000 tons combined output annoncé publiquement = inonde marché. "
                "Baseline 2026 : KAP voluntary cut 25-26.5kt (Bourse Direct 16/06/2026), "
                "value-over-volume strategy maintenue, 130Mlbs removed 2017-2025. Opposé "
                "de trigger actuellement."
            ),
        },
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        return 1

    cx = sqlite3.connect(DB)
    n_updated = 0
    n_skipped_idempotent = 0

    for ticker, idx_map in REWRITES.items():
        row = cx.execute(
            "SELECT id, invalidation_triggers FROM theses WHERE ticker=? AND status='active'",
            (ticker,),
        ).fetchone()
        if not row:
            print(f"  {ticker}: thesis not found, skip")
            continue
        thesis_id, raw = row
        triggers = json.loads(raw)
        changed = False
        for idx, payload in idx_map.items():
            current = triggers[idx]
            if payload["hint"] in current:
                # Still original wording — rewrite
                print(f"  {ticker} #{idx+1} : REWRITE")
                triggers[idx] = payload["new"]
                changed = True
            else:
                print(f"  {ticker} #{idx+1} : already rewritten, skip idempotent")
                n_skipped_idempotent += 1
        if changed and args.apply:
            cx.execute(
                "UPDATE theses SET invalidation_triggers = ? WHERE id = ?",
                (json.dumps(triggers, ensure_ascii=False), thesis_id),
            )
            n_updated += 1

    if args.apply:
        cx.commit()
    cx.close()

    print(f"\n═ Summary : {n_updated} theses UPDATE'd, {n_skipped_idempotent} skipped idempotent ═")
    if not args.apply:
        print("(dry-run, pass --apply pour modifier DB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
