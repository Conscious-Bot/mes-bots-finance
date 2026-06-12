"""Persist convictions + targets — 12/06/2026 (c) — UPDATE par id explicite.

Apres TODO élagage + #134 monitor stale_target, Olivier acte le book sur 4
facteurs (moat / asymétrie / thèse-intacte / falsifiable). Ce script
fige les changements dans theses. Backup DB obligatoire avant run.

Changements (12 UPDATE par id, transaction atomique, rowcount=1, read-back):

A) Convictions seules (7) :
   id=37 7011.T MHI       : conv 4 -> 5 + target 4488 JPY + stop 3150 JPY
   id=28 000660.KS SK     : conv 3 -> 4  (target/stop inchangés)
   id=43 SAF.PA           : conv 4 -> 3
   id=44 6857.T Advantest : conv 4 -> 3
   id=31 COHR             : conv 4 -> 3
   id=47 MP               : conv 4 -> 3
   id=35 STMPA.PA         : conv 3 -> 2

B) C5 targets/stops (3) :
   id=42 TSLA : conv 4 -> 5, target_full 468 -> 1075 USD, stop 335 -> 280 USD,
                + 4 invalidation_triggers JSON (FSD/Optimus/marges/dilution)
   id=29 SNPS : target_full NULL -> 700 USD, stop NULL -> 388 USD
   id=27 TSM  : target inchangé 495 USD, stop 305 -> 375 USD

C) Targets refraîchies dead -> live (2, EUR->USD au fx live get_fx_rate_on):
   id=34 ALAB : target 400 EUR -> USD, stop 340 EUR -> USD  (fx 12/06 = 1.1565)
   id=48 MU   : target 1050 EUR -> USD, stop 920 EUR -> USD

D) PENDING (ne pas toucher) : KLAC (prix DB cassé worldwide, fixer la source d'abord).

E) Franchise-hold (aucun changement) : ASML, Shin-Etsu, BESI, Lasertec.

Triggers : *_writeonce ne portent que sur entry_* (pas touchés ici). OK.
conviction_range : conv=2 (STMPA) accepté par le check.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from shared import prices, storage as s


def main():
    today = datetime.now(UTC).date().isoformat()
    fx = prices.get_fx_rate_on("EUR", "USD", today)
    if not fx or fx <= 0:
        raise RuntimeError(f"FX EUR/USD live indispo : {fx}")
    print(f"FX EUR/USD live ({today}) : {fx:.4f}")

    alab_target_usd = round(400 * fx, 2)
    alab_stop_usd = round(340 * fx, 2)
    mu_target_usd = round(1050 * fx, 2)
    mu_stop_usd = round(920 * fx, 2)

    updates = [
        {"id": 37, "tk": "7011.T", "set": {
            "conviction": 5,
            "target_full": 4488.0, "target_full_value": 4488.0,
            "target_full_currency": "JPY",
            "stop_price": 3150.0, "stop_value": 3150.0, "stop_currency": "JPY",
        }},
        {"id": 28, "tk": "000660.KS", "set": {"conviction": 4}},
        {"id": 43, "tk": "SAF.PA", "set": {"conviction": 3}},
        {"id": 44, "tk": "6857.T", "set": {"conviction": 3}},
        {"id": 31, "tk": "COHR", "set": {"conviction": 3}},
        {"id": 47, "tk": "MP", "set": {"conviction": 3}},
        {"id": 35, "tk": "STMPA.PA", "set": {"conviction": 2}},
        {"id": 42, "tk": "TSLA", "set": {
            "conviction": 5,
            "target_full": 1075.0, "target_full_value": 1075.0,
            "target_full_currency": "USD",
            "stop_price": 280.0, "stop_value": 280.0, "stop_currency": "USD",
            "invalidation_triggers": json.dumps([
                "FSD/robotaxi non-scalé fin 2027",
                "Optimus zéro traction fin 2027",
                "marges auto s'effondrent",
                "Musk dilue les porteurs Tesla",
            ]),
        }},
        {"id": 29, "tk": "SNPS", "set": {
            "target_full": 700.0, "target_full_value": 700.0,
            "target_full_currency": "USD",
            "stop_price": 388.0, "stop_value": 388.0, "stop_currency": "USD",
        }},
        {"id": 27, "tk": "TSM", "set": {
            "target_full": 495.0, "target_full_value": 495.0,
            "target_full_currency": "USD",
            "stop_price": 375.0, "stop_value": 375.0, "stop_currency": "USD",
        }},
        {"id": 34, "tk": "ALAB", "set": {
            "target_full": alab_target_usd, "target_full_value": alab_target_usd,
            "target_full_currency": "USD",
            "stop_price": alab_stop_usd, "stop_value": alab_stop_usd,
            "stop_currency": "USD",
        }},
        {"id": 48, "tk": "MU", "set": {
            "target_full": mu_target_usd, "target_full_value": mu_target_usd,
            "target_full_currency": "USD",
            "stop_price": mu_stop_usd, "stop_value": mu_stop_usd,
            "stop_currency": "USD",
        }},
    ]

    with s.db() as cx:
        try:
            for u in updates:
                cols = list(u["set"].keys())
                vals = [u["set"][c] for c in cols]
                set_clause = ", ".join(f"{c}=?" for c in cols)
                sql = f"UPDATE theses SET {set_clause} WHERE id=?"
                cur = cx.execute(sql, (*vals, u["id"]))
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"rowcount={cur.rowcount} pour id={u['id']} {u['tk']} "
                        f"(attendu 1) -- ROLLBACK"
                    )
                print(f"  ✓ id={u['id']:>3} {u['tk']:>12} : {len(cols)} champs updated")
            cx.commit()
            print(f"\n✓ COMMIT : {len(updates)} UPDATE")
        except sqlite3.IntegrityError as e:
            cx.rollback()
            print(f"\n✗ ROLLBACK sur IntegrityError (trigger writeonce ?) : {e}")
            raise
        except Exception as e:
            cx.rollback()
            print(f"\n✗ ROLLBACK : {e}")
            raise

    print("\n=== READ-BACK ===")
    with s.db() as cx:
        for u in updates:
            cols = list(u["set"].keys())
            sel = ", ".join(cols)
            row = cx.execute(f"SELECT {sel} FROM theses WHERE id=?", (u["id"],)).fetchone()
            row_dict = dict(zip(cols, row, strict=False))
            ok = all(row_dict[c] == u["set"][c] for c in cols)
            mark = "✓" if ok else "✗ DIVERGE"
            print(f"  {mark} id={u['id']:>3} {u['tk']:>12}")


if __name__ == "__main__":
    main()
