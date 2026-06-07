"""A backfill : fige l'etat T0 (snapshot 07/06 nuit) des theses actives dans
thesis_integrity_log.

Spec red-team DECISION_QUALITY_ENGINE : "decision_journal + verify_chain ->
backfill PIT des positions ouvertes". Fige le point-in-time MAINTENANT --
le look-ahead empoisonne toute reconstruction retroactive.

CAVEAT : ce backfill capture l'etat COURANT, pas l'etat HISTORIQUE entry.
Pour les theses ouvertes pre-pivot 07/06 nuit, variant_perception / driver_epic
/ benchmark sont NULL (champs ajoutes A0 aujourd'hui). C'est une realite
documentee : la chain commence ici, les theses anterieures n'ont pas de
pre-engagement structure (warning A0 sera surface lors de l'attribution).

Run : python3 scripts/backfill_thesis_integrity.py

Idempotence : si une these est deja dans thesis_integrity_log, skip
(detection via thesis_id existant + flag --force pour re-backfill).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_integrity")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="re-backfill meme si thesis_id deja en log")
    parser.add_argument("--status", default="active",
                        help="filter theses par status (default active)")
    args = parser.parse_args()

    from shared import storage

    # Read all theses
    with storage.db() as cx:
        rows = cx.execute(f"""
            SELECT id, ticker, direction, horizon, conviction, key_drivers,
                   invalidation_triggers, entry_price, target_price,
                   target_partial, target_full, stop_price, notes,
                   variant_perception, driver_epic, benchmark, opened_at
            FROM theses WHERE status='{args.status}'
            ORDER BY id ASC
        """).fetchall()
        # Get existing thesis_ids in log
        existing_ids = {
            r[0] for r in cx.execute(
                "SELECT DISTINCT thesis_id FROM thesis_integrity_log"
            ).fetchall()
        }

    log.info(
        f"{len(rows)} theses status='{args.status}', {len(existing_ids)} "
        "deja en thesis_integrity_log"
    )

    inserted = 0
    skipped = 0
    failed = 0
    for r in rows:
        thesis_id = r[0]
        if thesis_id in existing_ids and not args.force:
            skipped += 1
            continue

        # Build PIT payload from current thesis state
        try:
            key_drivers = json.loads(r[5]) if r[5] else []
            invalidation_triggers = json.loads(r[6]) if r[6] else []
            driver_epic_raw = r[14]
            if driver_epic_raw:
                try:
                    driver_epic = json.loads(driver_epic_raw)
                except json.JSONDecodeError:
                    driver_epic = driver_epic_raw
            else:
                driver_epic = None
        except Exception as e:
            log.warning(f"thesis {thesis_id} {r[1]} payload parse fail: {e}")
            failed += 1
            continue

        payload = {
            "thesis_id": thesis_id,
            "ticker": r[1],
            "direction": r[2],
            "horizon_days": r[3],
            "conviction": int(r[4]),
            "key_drivers": key_drivers,
            "invalidation_triggers": invalidation_triggers,
            "entry_price": float(r[7]) if r[7] is not None else None,
            "target_price": float(r[8]) if r[8] is not None else None,
            "target_partial": float(r[9]) if r[9] is not None else None,
            "target_full": float(r[10]) if r[10] is not None else None,
            "stop_price": float(r[11]) if r[11] is not None else None,
            "notes": r[12],
            # A0 pre-engagement fields (typically NULL for legacy theses)
            "variant_perception": r[13],
            "driver_epic": driver_epic,
            "benchmark": r[15],
            "opened_at": r[16],
            # Backfill metadata
            "_backfill_at": "2026-06-07T_PIVOT_NIGHT_",
            "_backfill_caveat": "PIT capture courant 07/06 nuit (pas historique entree)",
        }
        res = storage.insert_thesis_integrity_row(thesis_id, payload)
        if res is None:
            log.warning(f"thesis {thesis_id} {r[1]} insert FAILED")
            failed += 1
        else:
            inserted += 1
            log.info(
                f"  thesis {thesis_id} {r[1]} c{r[4]} -> seq {res['seq']} "
                f"hash {res['chain_hash'][:16]}..."
            )

    log.info(
        f"Backfill done: {inserted} inserted, {skipped} skipped, {failed} failed"
    )

    # Verify chain post-backfill
    from shared.integrity import verify_chain
    chain = storage.get_thesis_integrity_chain()
    ok, broken = verify_chain(chain)
    if ok:
        log.info(f"chain verify OK ({len(chain)} entries)")
    else:
        log.error(f"chain verify FAILED at seq={broken}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
