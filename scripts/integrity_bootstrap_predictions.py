#!/usr/bin/env python3
"""Bootstrap : chaine les predictions existantes dans prediction_integrity_log.

Etablit la baseline AUJOURD'HUI (n'antidate rien). One-shot avec idempotence-guard.
Puis : scripts/integrity_anchor.sh pour l'ancrage OTS du head chain.

Catch architecture (red-team 07/06 nuit++) : chain DISTINCT de thesis_integrity_log.
- payload_json (incl nonce 256 bits) reste PRIVE dans bot.db (gitignored)
- ledger public exporte hash chain seul (preserve hiding commit-reveal)
- nonce revele a la resolution de la prediction (outcome) -> tier recompute hash
"""

import json
import secrets
import sqlite3
import sys

from shared import integrity
from shared.storage import DB_PATH

COLS = (
    "id", "signal_id", "ticker", "direction", "horizon_days",
    "baseline_price", "baseline_date", "target_date",
    "probability_at_creation", "methodology_version", "created_at",
)


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM prediction_integrity_log"
        ).fetchone()[0]
        if existing:
            print(
                f"ABORT: prediction_integrity_log non vide ({existing} rows) "
                "-- bootstrap deja fait. Use --force pour re-bootstrap apres reset."
            )
            return 1
        rows = conn.execute(
            f"SELECT {','.join(COLS)} FROM predictions ORDER BY id ASC"
        ).fetchall()
        if not rows:
            print("ABORT: aucune prediction en DB, rien a ancrer")
            return 1

        prev = integrity.GENESIS_HASH
        for r in rows:
            payload = dict(zip(COLS, r, strict=True))
            payload["nonce"] = secrets.token_hex(32)
            prev_used, chain_hash = integrity.chain_append(prev, payload)
            conn.execute(
                "INSERT INTO prediction_integrity_log "
                "(prediction_id, payload_json, prev_hash, chain_hash) "
                "VALUES (?,?,?,?)",
                (
                    payload["id"],
                    json.dumps(payload, sort_keys=True),
                    prev_used,
                    chain_hash,
                ),
            )
            prev = chain_hash
        conn.commit()

        # Verify chain post-bootstrap
        chain = [
            dict(zip(
                ("seq", "prediction_id", "captured_at", "payload_json",
                 "prev_hash", "chain_hash"),
                x,
                strict=True,
            ))
            for x in conn.execute(
                "SELECT seq,prediction_id,captured_at,payload_json,prev_hash,chain_hash "
                "FROM prediction_integrity_log ORDER BY seq"
            )
        ]
        ok, broken = integrity.verify_chain(chain)
        status = "OK" if ok else f"CASSE seq={broken}"
        print(
            f"bootstrap: {len(rows)} predictions | "
            f"head={prev[:12]}... | verify={status}"
        )
        return 0 if ok else 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
