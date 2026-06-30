"""One-off VM : nettoie les triggered_*_at orphelins (audit chrono 30/06).

CONTEXTE
--------
price_monitor pose triggered_{partial,full,stop}_at au franchissement d'un niveau
et se garde de re-tirer via `and not triggered_*_at`. Quand le sweep #135 a RELEVÉ
les cibles, les flags posés contre les ANCIENNES cibles n'ont pas été reset → le
garde supprime SILENCIEUSEMENT l'alerte contre le NOUVEAU niveau (5 thèses : prix
à 53-84% de la cible courante, flag full pourtant posé).

Le source-fix (storage.update_thesis_field, commit 69fea42) empêche la péremption
FUTURE. Ce script nettoie les flags DÉJÀ orphelins en prod.

CRITÈRE (mirror exact de price_monitor, direction-aware)
-------------------------------------------------------
On clear un triggered_X_at SET si le prix ne satisfait PAS actuellement le
franchissement du niveau courant :
  long  : full/partial si last_price < target ; stop si last_price > stop_price
  short : inverse
Clearer est TOUJOURS sûr : price_monitor ne re-tire que sur franchissement réel,
donc au pire on ré-arme une alerte correcte. Aucun faux positif possible.

DOCTRINE
--------
À lancer sur la VM (single-source : la VM est autoritative, le Mac est read-only ;
un nettoyage côté Mac serait écrasé au prochain sync). Backup + before/after +
count-assert. Pas de recreate-table → pas de bot-stop requis (UPDATE bénin,
concurrent-safe avec le cron price_monitor).

    python -m scripts.clear_stale_triggers_2026-07-01          # applique
    python -m scripts.clear_stale_triggers_2026-07-01 --dry    # simulation
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime

from shared import storage

_LEVELS = (
    ("triggered_partial_at", "target_partial"),
    ("triggered_full_at", "target_full"),
    ("triggered_stop_at", "stop_price"),
)


def _is_stale(direction: str, flag_col: str, level_col: str, price: float, level: float) -> bool:
    """True si le flag est posé mais le prix ne franchit PAS le niveau courant."""
    long = (direction or "long").lower() == "long"
    if flag_col == "triggered_stop_at":
        # stop franchi = prix passe SOUS (long) / AU-DESSUS (short) le stop.
        return price > level if long else price < level
    # partial / full = prix atteint AU-DESSUS (long) / EN-DESSOUS (short) la cible.
    return price < level if long else price > level


def main() -> int:
    dry = "--dry" in sys.argv
    db_path = storage.DB_PATH
    print(f"DB = {db_path}  ({'DRY-RUN' if dry else 'APPLY'})\n")

    if not dry:
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup = f"{db_path}.backup_clear_triggers_{stamp}"
        shutil.copy2(db_path, backup)
        print(f"backup -> {backup}\n")

    to_clear: list[tuple[int, str, str]] = []  # (thesis_id, ticker, flag_col)
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT id, ticker, direction, last_price, "
            "triggered_partial_at, triggered_full_at, triggered_stop_at, "
            "target_partial, target_full, stop_price "
            "FROM theses WHERE status='active'"
        ).fetchall()

        for r in rows:
            price = r["last_price"]
            if price is None:
                continue
            for flag_col, level_col in _LEVELS:
                flag = r[flag_col]
                level = r[level_col]
                if flag and level and _is_stale(r["direction"], flag_col, level_col, price, level):
                    to_clear.append((r["id"], r["ticker"], flag_col))
                    pct = 100.0 * price / level
                    print(f"  STALE  {r['ticker']:11s} {flag_col:22s} "
                          f"posé={str(flag)[:19]}  prix={price:g} vs {level_col}={level:g} ({pct:.0f}%)")

        print(f"\n{len(to_clear)} flag(s) orphelin(s) détecté(s).")
        if not to_clear:
            print("rien à nettoyer.")
            return 0

        if dry:
            print("DRY-RUN : aucun write.")
            return 0

        for thesis_id, _tk, flag_col in to_clear:
            cx.execute(f"UPDATE theses SET {flag_col}=NULL WHERE id=?", (thesis_id,))
        cx.commit()

        # count-assert : tous les flags ciblés doivent être NULL post-update.
        remaining = 0
        for thesis_id, _tk, flag_col in to_clear:
            v = cx.execute(f"SELECT {flag_col} FROM theses WHERE id=?", (thesis_id,)).fetchone()[0]
            if v is not None:
                remaining += 1
        if remaining:
            raise RuntimeError(f"ABORT : {remaining} flag(s) non-clearés après UPDATE (incohérence)")

    print(f"\nOK : {len(to_clear)} flag(s) clearé(s). price_monitor ré-alertera au prochain "
          "franchissement réel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
