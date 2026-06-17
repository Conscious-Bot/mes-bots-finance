"""Rewrite AVGO thesis trigger #1 — fix false-positive S10 cross-ref (17/06/2026).

## Context

Le mécanisme cross-ref invalidation_triggers ↔ sentinelles résolues (commit
`05c8d22` 16/06) a marqué AVGO trigger #1 fired via résolution sentinelle S10
("Google confirme dual-sourcing TPU hors Broadcom"). Verdict initial Claude
red-team : alleger ~30%.

## Fact-check Bigdata.com 17/06

Investigation #135 méthode 3 colonnes a révélé que le verdict initial était
basé sur des données partielles (Memeburn 16/06 mentionnait Samsung/MediaTek
pour Icefish I/O die, j'avais conclu "Broadcom déplacé"). Sources canoniques
Edgar/transcripts montrent l'OPPOSÉ :

- **Edgar 8-K 6 avril 2026** : Broadcom-Google **Long Term Agreement** explicite
  pour développer + supplier custom TPUs "future generations" jusqu'à 2031.
- **Q2 FY26 earnings (Quartr 3 juin 2026)** :
  - AI semi revenue Q2 : **$10.8B (+143% YoY)**
  - Bookings AI Q2 : **$30B** (vs $10.8B shippé)
  - Q3 guidance AI semi : **$16B (+200% YoY)**
  - FY26 AI semi guidance : **$56B (+180% YoY)**
  - FY27 réaffirmé : **$100B+**
  - Anthropic 3.5 GW additional via Broadcom pour 2027
  - Apollo+Blackstone 20 GW deployment jusqu'à 2028 ($35B first tranche)
- CEO Q2 call : "Our relationship [with Google] continues to be **strategic and
  very substantial**... vastly superior technology and execution compared to
  other alternatives."

L'Icefish v10 dual-sourcing concerne le **I/O die** (sub-component), PAS le
custom silicon core. Le bear-claim "AVGO ASIC revenue at risk" est **inexistant
à l'horizon visible** (24+ mois).

## Cure : réécriture trigger #1

**AVANT** :
> "S10 dual-sourcing TPU (bear-claim core) : si GOOGL annonce TPU v6/v7 produit
> par MRVL ou AMD = AVGO ASIC revenue at risk -> 25-35% du backlog $110Md dépend
> du custom silicon hyperscaler"

Problème :
- Wording trop spécifique ("v6/v7", "MRVL ou AMD") → mécaniquement fired sur
  événement non-équivalent (Icefish v10, MediaTek pour I/O die)
- Code "S10" parsed par cross-ref helper → faux positif persistant

**APRÈS** :
> "AI semi revenue Q3 2026 < $14B OR FY26 cumulative AI semi < $50B (vs guidance
> $16B / $56B respectivement) = signal de rupture pricing/volume custom silicon
> hyperscaler. Bear-claim core : 25-35% du backlog dépend du custom silicon
> Google/Meta/Anthropic/OpenAI ; miss matériel = re-rating thèse."

Avantages :
- Mesurable directement sur les earnings prints AVGO (objectif, pas
  interprétation)
- Forward-looking (next 2 calls Q3 09/26 + Q4 12/26)
- Pas de code "S{N}" → pas de cross-ref false-positive
- Critères tied au CORE de la thèse (custom silicon revenue, pas un sub-component)

## Verdict action AVGO révisé

**WAIT** (pas alleger). Le trigger fired était mécanique sur un événement
sémantiquement proche mais structurellement non-érosif. Conviction c3 maintenue,
ne pas trim.

## Idempotence

Le script vérifie le contenu actuel du trigger #1 avant UPDATE. Si déjà la
nouvelle version, skip.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "bot.db"

OLD_TRIGGER_HINT = "S10 dual-sourcing TPU"  # détection idempotence
NEW_TRIGGER = (
    "AI semi revenue Q3 2026 < $14B OR FY26 cumulative AI semi < $50B "
    "(vs guidance $16B / $56B respectivement) = signal de rupture pricing/volume "
    "custom silicon hyperscaler. Bear-claim core : 25-35% du backlog dépend du "
    "custom silicon Google/Meta/Anthropic/OpenAI ; miss matériel = re-rating thèse."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        return 1

    cx = sqlite3.connect(DB)
    row = cx.execute(
        "SELECT id, invalidation_triggers FROM theses WHERE ticker='AVGO'"
    ).fetchone()
    if not row:
        print("ERROR: AVGO thesis not found", file=sys.stderr)
        return 1

    thesis_id, raw = row
    triggers = json.loads(raw)

    if OLD_TRIGGER_HINT not in triggers[0]:
        print(
            f"Trigger #1 AVGO déjà réécrit (no S10 hint). Skip idempotent.\n"
            f"  Current #1: {triggers[0][:120]}..."
        )
        return 0

    print("═ AVGO trigger #1 rewrite — fix S10 false-positive ═\n")
    print(f"AVANT (#{thesis_id}):")
    print(f"  {triggers[0]}\n")
    print("APRÈS:")
    print(f"  {NEW_TRIGGER}\n")

    if args.apply:
        triggers[0] = NEW_TRIGGER
        cx.execute(
            "UPDATE theses SET invalidation_triggers = ? WHERE id = ?",
            (json.dumps(triggers, ensure_ascii=False), thesis_id),
        )
        cx.commit()
        print("→ APPLIED")
    else:
        print("(dry-run, pass --apply pour modifier DB)")

    cx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
