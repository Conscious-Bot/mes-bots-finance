import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Smoke test Phase 11: run_enhanced_digest() x3 + verifier persist + dedup."""
import sqlite3

from intelligence import digest
from shared import storage

DB = "data/bot.db"

def n_rows():
    conn = sqlite3.connect(DB)
    n = conn.execute("SELECT COUNT(*) FROM conviction_history").fetchone()[0]
    conn.close()
    return n

def main():
    print("=== Phase 11 Idempotency Smoke Test ===\n")

    before = n_rows()
    print(f"BEFORE: {before} rows in conviction_history\n")

    msgs = []
    for i in range(1, 4):
        msg = digest.run_enhanced_digest(limit=15, top_n=5)
        n = n_rows()
        msgs.append(msg)
        print(f"After run #{i}: {n} rows  (cumulative +{n - before})")

    after = n_rows()
    growth = after - before
    print(f"\nNet growth: +{growth} rows over 3 runs")
    print(f"Avg per run: {growth/3:.0f} rows (expected ~15-20)")

    # Dedup check via lecture
    tops = storage.get_top_material_signals(n=5, since_hours=24)
    ids = [t["id"] for t in tops]
    if len(ids) == len(set(ids)):
        print(f"\nPASS dedup: get_top_material_signals returne {len(ids)} signaux uniques")
    else:
        print(f"\nFAIL dedup: duplicats detectes -> {ids}")

    # Consistance taille output
    sizes = [len(m) for m in msgs]
    delta = max(sizes) - min(sizes)
    if delta < 300:
        print(f"PASS consistance: tailles {sizes}, delta {delta} chars (tolerance 300)")
    else:
        print(f"WARN: tailles varient significativement {sizes}, delta {delta}")

    # Bloat ceiling check
    if growth <= 60:
        print(f"PASS bloat: +{growth} <= 60 attendu pour 3 runs")
    else:
        print(f"FAIL bloat: +{growth} excede attendu (60), persist peut-etre non-borne")

    print("\nDone.")

if __name__ == "__main__":
    main()
