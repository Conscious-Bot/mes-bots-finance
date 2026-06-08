"""One-shot script : restore natives baselines depuis backup pré-corruption.

Cf SPEC_MONEY_INVARIANT.md §6.3 + red-team Olivier 08/06 nuit :
  "Migration 0045 = schéma SEULEMENT (portable). Restore = script one-shot
   scripts/restore_native_baselines.py : backfill natif depuis backup,
   idempotent-gardé (skip si déjà restauré), lancé une fois sur la vraie DB."

Ce script :
  1. Vérifie qu'il n'a pas déjà été appliqué (idempotent : skip si entry_value
     non-NULL pour la majorité des thèses → restore déjà fait).
  2. ATTACH backup propre 06/06 (data/bot.db.backup_session_close_20260606_192531).
  3. UPDATE theses + positions : copie entry_price/stop_price/target_partial/
     target_full/avg_cost depuis backup vers les colonnes _value.
  4. Set _currency dérivée du ticker (.T→JPY, .KS→KRW, .PA/.AS→EUR, défaut USD).
  5. Set _asof = opened_at de la thèse / opened_at de la position.
  6. SYNC les colonnes legacy float-nues avec les natives restaurées
     (pendant la migration étagée — gate ratchet décroitra).
  7. DETACH backup.

USAGE :
    python3 scripts/restore_native_baselines.py [--db data/bot.db] [--dry-run]

Le script est :
  - Idempotent : peut être relancé sans dommage (skip si déjà restauré).
  - One-shot : pas un mécanisme permanent. Acte de recovery pré-spec.
  - Séparé de la migration alembic : la migration est portable, le restore
    dépend d'un backup local et est lancé manuellement sur prod.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "bot.db"
BACKUP_PATH = ROOT / "data" / "bot.db.backup_session_close_20260606_192531"


def _currency_case_sql(ticker_col: str) -> str:
    return f"""
        CASE
            WHEN {ticker_col} LIKE '%.T' THEN 'JPY'
            WHEN {ticker_col} LIKE '%.KS' THEN 'KRW'
            WHEN {ticker_col} LIKE '%.PA' THEN 'EUR'
            WHEN {ticker_col} LIKE '%.AS' THEN 'EUR'
            ELSE 'USD'
        END
    """.strip()


def is_already_restored(conn: sqlite3.Connection) -> bool:
    """Idempotent guard : si une majorité des thèses ouvertes ont entry_value non-NULL,
    le restore a déjà été appliqué."""
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN entry_value IS NOT NULL THEN 1 ELSE 0 END) AS n_restored,
            COUNT(*) AS n_total
        FROM theses WHERE status = 'active'
    """).fetchone()
    if not row or row[1] == 0:
        return False
    return row[0] >= row[1] * 0.5  # >= 50% restored = considered done


def restore(db_path: Path, dry_run: bool = False) -> int:
    """Apply restore. Returns 0 if OK, non-zero on error."""
    if not BACKUP_PATH.exists():
        print(f"ERROR: backup file not found at {BACKUP_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        if is_already_restored(conn):
            print(f"OK: {db_path} déjà restaurée (entry_value non-NULL pour ≥50% des actives) — skip")
            return 0

        if dry_run:
            print(f"[dry-run] aurait restauré natives depuis {BACKUP_PATH} vers {db_path}")
            return 0

        print(f"Restoring natives from {BACKUP_PATH.name} into {db_path.name}...")
        conn.execute(f"ATTACH DATABASE '{BACKUP_PATH}' AS bk")

        # Restore theses
        conn.execute(f"""
            UPDATE theses
            SET
                entry_value = (SELECT bk_t.entry_price FROM bk.theses bk_t WHERE bk_t.id = theses.id),
                entry_currency = {_currency_case_sql("theses.ticker")},
                entry_asof = theses.opened_at,
                stop_value = (SELECT bk_t.stop_price FROM bk.theses bk_t WHERE bk_t.id = theses.id),
                stop_currency = {_currency_case_sql("theses.ticker")},
                stop_asof = theses.opened_at,
                target_partial_value = (SELECT bk_t.target_partial FROM bk.theses bk_t WHERE bk_t.id = theses.id),
                target_partial_currency = {_currency_case_sql("theses.ticker")},
                target_partial_asof = theses.opened_at,
                target_full_value = (SELECT bk_t.target_full FROM bk.theses bk_t WHERE bk_t.id = theses.id),
                target_full_currency = {_currency_case_sql("theses.ticker")},
                target_full_asof = theses.opened_at
            WHERE EXISTS (SELECT 1 FROM bk.theses bk_t WHERE bk_t.id = theses.id)
        """)

        # Restore positions.avg_cost
        conn.execute(f"""
            UPDATE positions
            SET
                avg_cost_value = (SELECT bk_p.avg_cost FROM bk.positions bk_p WHERE bk_p.ticker = positions.ticker AND bk_p.status='open'),
                avg_cost_currency = {_currency_case_sql("positions.ticker")},
                avg_cost_asof = positions.opened_at
            WHERE EXISTS (SELECT 1 FROM bk.positions bk_p WHERE bk_p.ticker = positions.ticker AND bk_p.status='open')
        """)

        # SYNC legacy float-nues avec natives restaurees (decreasing ratchet pendant migration)
        conn.execute("UPDATE theses SET entry_price = entry_value WHERE entry_value IS NOT NULL")
        conn.execute("UPDATE theses SET stop_price = stop_value WHERE stop_value IS NOT NULL")
        conn.execute("UPDATE theses SET target_partial = target_partial_value WHERE target_partial_value IS NOT NULL")
        conn.execute("UPDATE theses SET target_full = target_full_value WHERE target_full_value IS NOT NULL")
        conn.execute("UPDATE positions SET avg_cost = avg_cost_value WHERE avg_cost_value IS NOT NULL")

        conn.commit()
        conn.execute("DETACH DATABASE bk")
        conn.commit()

        # Verify
        row = conn.execute(
            "SELECT COUNT(*) FROM theses WHERE status='active' AND entry_value IS NOT NULL"
        ).fetchone()
        print(f"OK: restored {row[0]} theses with entry_value non-NULL")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=str(DEFAULT_DB), help="DB path (default: data/bot.db)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return restore(Path(args.db), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
