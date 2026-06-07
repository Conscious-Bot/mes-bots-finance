"""Backfill 4 chokepoints en position_type='structural' avec justification.

Spec user red-team 07/06 :
Les 4 lignes pour lesquelles on a deja DROP stop_price (erreur categorie
chokepoint structurel) doivent etre TAGGEES structural avec justification
verifiable. Le hook tamper-evident append au thesis_integrity_log -> trace
immuable de pourquoi on les considere structurelles.

Idempotent : si une these est deja structural, le hook le re-confirme
(nouvelle entree chain). Sans-effet si re-execute apres assignation initiale.

Usage : python3 scripts/backfill_chokepoints_structural.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_chokepoints")


_CHOKEPOINTS: dict[str, dict] = {
    "ASML.AS": {
        "structural_justification": (
            "Monopole EUV lithography. Seul fournisseur mondial systemes "
            "lithographie EUV niveau 7nm/5nm/3nm. Verifiable : Canon et "
            "Nikon n'ont AUCUN systeme EUV en production. Cycle dev systeme "
            "EUV ~15-20 ans. Invalidation = nouveau competiteur EUV livre "
            "en volume chez foundry tier-1 (TSM/Samsung/Intel)."
        ),
        "tags": ["mega_cap"],
    },
    "TSM": {
        "structural_justification": (
            "Quasi-monopole foundry leading-edge (N3/N2). 90%+ part de "
            "marche edge production AI accelerators (NVDA/AMD/AAPL/Broadcom). "
            "Verifiable : Samsung N2 rendement non-confirme, Intel 18A "
            "client list lean. Invalidation = Samsung N2 ramp confirme "
            "production volume + design wins majeurs OU Intel 18A clients "
            "top-10 publies."
        ),
        "tags": ["mega_cap"],
    },
    "SNPS": {
        "structural_justification": (
            "Duopoly EDA avec Cadence (CDNS) sur design IC complexes. ~50-55% "
            "PdM EDA + acquisition Ansys (simulation multi-physique). "
            "Verifiable : tout chip leading-edge (NVDA H/B, AMD MI, AAPL M, "
            "Intel) passe par SNPS ou CDNS. Invalidation = open-source EDA "
            "(OpenROAD, Magic) gagne design win majeur en production OU "
            "Cadence prend part de marche > 5pp documente."
        ),
        "tags": [],
    },
    "6920.T": {
        "structural_justification": (
            "Quasi-monopole inspection masque EUV actinique. Seul fournisseur "
            "systemes mesure defauts masque EUV pre-fabrication. Verifiable : "
            "KLA et Applied Materials n'ont PAS de solution actinique en "
            "production. Tous masques EUV des foundries passent par Lasertec. "
            "Invalidation = KLA/AMAT livrent systeme inspection actinique "
            "en volume chez TSM/Samsung OU foundry passe a inspection non-"
            "actinique (degrade qualite acceptee)."
        ),
        "tags": [],
    },
}


def main() -> int:
    from shared import storage

    log.info(f"Backfill {len(_CHOKEPOINTS)} chokepoints structural...")
    n_ok = 0
    n_fail = 0
    for ticker, spec in _CHOKEPOINTS.items():
        try:
            thesis = storage.get_thesis_by_ticker(ticker)
            if not thesis:
                log.warning(f"  {ticker}: NO active thesis -- skip")
                continue
            tid = thesis["id"]
            result = storage.set_position_type(
                tid,
                "structural",
                structural_justification=spec["structural_justification"],
                position_tags=spec["tags"],
            )
            if result:
                log.info(
                    f"  {ticker} (id={tid}): structural OK "
                    f"integrity_seq={result.get('integrity_seq')} "
                    f"hash={result.get('integrity_hash', '')[:16]}..."
                )
                n_ok += 1
            else:
                log.warning(f"  {ticker}: set_position_type returned None")
                n_fail += 1
        except Exception as e:
            log.error(f"  {ticker}: FAILED {type(e).__name__}: {e}")
            n_fail += 1

    log.info(f"Done : {n_ok} ok, {n_fail} fail")
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
