"""Back-fill positions_meta depuis positions table existante.

Cf SPEC_LEDGER.md §5 étape 0047 : la VUE positions (post-0048) joint
positions_meta pour les 5 colonnes déclarées (ticker, notes, status,
account, wrapper). Sans positions_meta peuplé, la VUE perdrait ces
métadonnées.

Idempotent :
  - Ne touche pas les rows déjà en positions_meta (INSERT ON CONFLICT DO NOTHING)
  - Re-runnable sans risque
  - 0 transactions touchées (n'écrit que dans positions_meta)

Audit log : pas d'audit per ticker (c'est une migration de masse triviale,
les valeurs viennent direct de positions). L'audit est dans le commit git.

Usage : python3 scripts/migrate_positions_meta_from_positions.py
"""
from __future__ import annotations

import sys

from shared import storage


def main() -> int:
    with storage.db() as cx:
        cx.row_factory = None

        # Vérif pré-flight : table positions_meta existe (migration 0046 appliquée)
        r = cx.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='positions_meta'"
        ).fetchone()
        if not r:
            print("ERREUR : table positions_meta absente — appliquer migration 0046 d'abord.")
            return 1

        # Source : positions table (qty>0 status=open ET historique closed pour préserver
        # la métadonnée des positions sorties — utile pour audit post-swap).
        rows = cx.execute("""
            SELECT ticker, notes, status, account, wrapper
            FROM positions
        """).fetchall()

        inserted = 0
        skipped = 0
        for ticker, notes, status, account, wrapper in rows:
            # INSERT OR IGNORE : idempotence sur PRIMARY KEY ticker
            cursor = cx.execute("""
                INSERT OR IGNORE INTO positions_meta (ticker, notes, status, account, wrapper)
                VALUES (?, ?, ?, ?, ?)
            """, (ticker, notes, status, account, wrapper))
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        cx.commit()

        # Sanity : count après
        n = cx.execute("SELECT COUNT(*) FROM positions_meta").fetchone()[0]
        print(f"positions_meta : {inserted} inserted, {skipped} skipped (already present)")
        print(f"total rows in positions_meta : {n}")
        print(f"source positions table : {len(rows)} rows scanned")

        # Vérif que les 26 open sont bien représentées
        n_open_meta = cx.execute("""
            SELECT COUNT(*) FROM positions_meta m
            JOIN positions p ON p.ticker = m.ticker
            WHERE p.status = 'open' AND p.qty > 0
        """).fetchone()[0]
        print(f"open positions (qty>0) couvertes dans meta : {n_open_meta}/26 attendu")

        if n_open_meta < 26:
            print(f"⚠ {26 - n_open_meta} positions ouvertes sans meta — vérifier état.")
            return 2

        return 0


if __name__ == "__main__":
    sys.exit(main())
