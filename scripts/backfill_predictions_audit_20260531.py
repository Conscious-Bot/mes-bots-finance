"""Backfill prediction_audit_log avec les 3 mutations du 31/05/2026.

Strategie : on a re-resolu NVDA 50, AVGO 51, MSFT 53 ce matin via le fix
ground-truth (commit bce5a58). L'ancien outcome 'neutral' a ete OVERWRITE
sans audit trail en DB. La migration 0022 cree la table prediction_audit_log
mais ne backfill pas (separation : migration = schema, backfill = data).

Ce script reconstruit le trail :
- Pour chaque (50, 51, 53), lit l'ancien snapshot depuis le backup DB
  `data/bot.db.backup_pre_resolve_fix_20260531_152531` (l'etat ANTE fix)
- Lit le snapshot actuel depuis la prod DB (l'etat POST fix)
- Insere 2 rows audit log :
  * event_type='re_resolve_pre' avec snapshot ANTE + occurred_at=2026-05-29T07:00 (date originale)
  * event_type='re_resolve' avec snapshot POST + occurred_at=2026-05-31T15:25 (moment du fix)
- Source = 'manual:claude_opus_47'
- Actor = 'session_31_05_2026_ground_truth_fix'

Use case : invoque UNE seule fois apres la migration 0022. Idempotent via
verification que les 2 rows ANTE n'existent pas deja (DELETE + reinsert
serait plus sale, on prefere check + skip).
"""

import json
import sqlite3
import sys

DB = "data/bot.db"
BACKUP = "data/bot.db.backup_pre_resolve_fix_20260531_152531"
PIDS = [50, 51, 53]
ANTE_TS = "2026-05-29 07:00:00"  # quand le bot avait resolu (mais avec mauvais prix T-1)
POST_TS = "2026-05-31 15:25:31"  # quand le fix a tourne (commit bce5a58 horaire)
SOURCE = "manual:claude_opus_47"
ACTOR = "session_31_05_2026_ground_truth_fix"


def main() -> int:
    prod = sqlite3.connect(DB)
    backup = sqlite3.connect(BACKUP)
    try:
        for pid in PIDS:
            existing = prod.execute(
                "SELECT COUNT(*) FROM prediction_audit_log WHERE prediction_id=? AND actor=?",
                (pid, ACTOR),
            ).fetchone()[0]
            if existing >= 2:
                print(f"pid={pid}: deja backfille ({existing} rows), skip")
                continue

            ante = backup.execute(
                "SELECT resolved_at, final_price, return_pct, outcome, "
                "       credibility_delta, brier_score FROM predictions WHERE id=?",
                (pid,),
            ).fetchone()
            post = prod.execute(
                "SELECT resolved_at, final_price, return_pct, outcome, "
                "       credibility_delta, brier_score FROM predictions WHERE id=?",
                (pid,),
            ).fetchone()
            if ante is None or post is None:
                print(f"pid={pid}: introuvable (ante={ante} post={post}), skip")
                continue

            ante_payload = {
                "resolved_at": ante[0], "final_price": ante[1],
                "return_pct": ante[2], "outcome": ante[3],
                "credibility_delta": ante[4], "brier_score": ante[5],
            }
            post_payload = {
                "resolved_at": post[0], "final_price": post[1],
                "return_pct": post[2], "outcome": post[3],
                "credibility_delta": post[4], "brier_score": post[5],
            }

            prod.execute(
                "INSERT INTO prediction_audit_log "
                "(prediction_id, event_type, occurred_at, payload_json, source, actor) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, "re_resolve_pre", ANTE_TS, json.dumps(ante_payload), SOURCE, ACTOR),
            )
            prod.execute(
                "INSERT INTO prediction_audit_log "
                "(prediction_id, event_type, occurred_at, payload_json, source, actor) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, "re_resolve", POST_TS, json.dumps(post_payload), SOURCE, ACTOR),
            )
            print(f"pid={pid}: backfille (ante outcome={ante[3]} -> post outcome={post[3]})")

        prod.commit()
        # Verif final
        n = prod.execute(
            "SELECT COUNT(*) FROM prediction_audit_log WHERE actor=?", (ACTOR,),
        ).fetchone()[0]
        print(f"\nTotal rows audit pour {ACTOR} : {n}")
        return 0
    finally:
        prod.close()
        backup.close()


if __name__ == "__main__":
    sys.exit(main())
