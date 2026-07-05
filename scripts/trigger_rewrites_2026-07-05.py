#!/usr/bin/env python3
"""Audit-trace idempotent — triggers-check hebdo 2026-07-05.

Rewrite unique ce round : SNPS T1 « Ansys merger blocked antitrust » devenu
OBSOLÈTE — le deal Synopsys/Ansys a CLÔTURÉ (juillet 2025, toutes approbations
+ consent order FTC 10/2025, cessions optical/photonic/RTL power à Keysight).
Le risque « bloqué antitrust » ne peut plus se matérialiser. On requalifie le
trigger vers le risque résiduel réel post-clôture : échec d'intégration /
synergies cross-sell EDA+multiphysics sous plan (mesurable, 2 quarters).

Idempotent : assert count==1 sur le vieux texte AVANT update ; si déjà réécrit
(ou absent), skip sans erreur. Run sur VM authoritative (single-source doctrine).

0/89 triggers fired ce round ; couche macro massivement favorable (hyperscaler
capex +77% YoY, HBM sold-out, NdPr +136%, uranium cut, ReArm EU €800B). Détail
dans SESSION_STATE ## Triggers check 2026-07-05.

Side-flag NON traité ici (décision de risque à Olivier, pas un rewrite de
wording) : ENTG stop_price=165 casse l'invariant long (stop>entry 135>partial
159). À recalculer par décision humaine, pas invention.
"""
import json
import sqlite3

from shared.storage import DB_PATH

_OLD = "Ansys merger blocked antitrust."
_NEW = (
    "Synergies Ansys ratées : cross-sell EDA+multiphysics <guidance sur 2 quarters "
    "consécutifs (intégration post-clôture 07/2025 échoue) OR fuite clients matérielle "
    "post-cessions Keysight (optical/photonic/RTL power divestis FTC 10/2025)"
)


def main() -> None:
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    row = cx.execute(
        "SELECT invalidation_triggers FROM theses WHERE ticker='SNPS' AND status='active'"
    ).fetchone()
    if not row:
        print("SNPS : thèse active introuvable — skip")
        return
    trigs = json.loads(row["invalidation_triggers"]) if row["invalidation_triggers"] else []
    if _NEW in trigs:
        print("SNPS T1 : déjà réécrit — idempotent skip")
        return
    n = trigs.count(_OLD)
    if n != 1:
        print(f"SNPS T1 : ancien texte trouvé {n}× (attendu 1) — ABORT, aucune écriture")
        return
    idx = trigs.index(_OLD)
    trigs[idx] = _NEW
    cx.execute(
        "UPDATE theses SET invalidation_triggers=? WHERE ticker='SNPS' AND status='active'",
        (json.dumps(trigs, ensure_ascii=False),),
    )
    cx.commit()
    print(f"SNPS T1 réécrit (idx {idx}) :\n  OLD: {_OLD}\n  NEW: {_NEW}")


if __name__ == "__main__":
    main()
