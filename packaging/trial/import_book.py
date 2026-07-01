"""import_book — seed d'une instance PRESAGE trial depuis un CSV simple.

« Rentre tes lignes + thèses, tout se met en place. » Lit `book.csv` (une ligne
= une position + sa thèse optionnelle), écrit dans les tables canoniques, et
backfille l'historique de prix pour que le dashboard affiche des vrais prix.

Rappel d'archi :
  - `positions` est une VUE dérivée de `transactions` → on ne l'écrit JAMAIS
    directement. On insère un BUY dans `transactions` + une ligne `positions_meta`.
  - `price_history` est alimentée par un cron du bot en prod. En trial (pas de bot),
    on backfille one-shot via `shared.prices.ensure_price_history` — SANS ça, la vue
    n'a pas de `last_price` et le dashboard est vide.

Usage :
    python import_book.py book.csv           # importe
    python import_book.py book.csv --dry      # simulation, 0 write

Colonnes CSV (header requis) :
  POSITION (obligatoire) : ticker, qty, avg_price_native, currency, trade_date
  THÈSE (optionnel)      : conviction, direction, entry_price, target_partial,
                           target_full, stop_price, thesis
  META (optionnel)       : account, wrapper
Idempotent : un ticker déjà présent (positions_meta) est sauté.
"""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime, timedelta

from shared import prices, storage

_BACKFILL_DAYS = 400  # ~13 mois : couvre daily%/semaine/mois + sparkline equity


def _f(row: dict, key: str) -> float | None:
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _fx_to_eur(currency: str) -> float:
    """FX native→EUR pour fx_at_trade. EUR=1.0 ; sinon best-effort, fallback 1.0."""
    cur = (currency or "EUR").upper()
    if cur == "EUR":
        return 1.0
    try:
        rate = prices.get_fx_rate(cur, "EUR")
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    print(f"  [warn] FX {cur}→EUR indisponible, fx_at_trade=1.0 (valeurs EUR approximatives)")
    return 1.0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if not args:
        print("usage: python import_book.py book.csv [--dry]")
        return 2
    path = args[0]

    with open(path, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("ticker") or "").strip()]
    print(f"{len(rows)} ligne(s) dans {path}  ({'DRY-RUN' if dry else 'IMPORT'})\n")

    now = datetime.now(UTC).isoformat(timespec="seconds")
    today = datetime.now(UTC).date()
    start = (today - timedelta(days=_BACKFILL_DAYS)).isoformat()
    n_pos = n_thesis = n_skip = 0
    tickers: list[str] = []

    with storage.db() as cx:
        existing = {r[0] for r in cx.execute("SELECT ticker FROM positions_meta")}
        for r in rows:
            tk = r["ticker"].strip().upper()
            if tk in existing:
                print(f"  [skip] {tk} déjà présent (positions_meta)")
                n_skip += 1
                continue
            qty = _f(r, "qty")
            px = _f(r, "avg_price_native")
            cur = (r.get("currency") or "EUR").strip().upper()
            trade_date = (r.get("trade_date") or today.isoformat()).strip()
            if qty is None or px is None:
                print(f"  [warn] {tk} : qty/avg_price_native manquant → sauté")
                n_skip += 1
                continue
            fx = _fx_to_eur(cur)
            print(f"  {tk}: {qty} @ {px} {cur} (fx→EUR {fx:.4f})")
            tickers.append(tk)
            if dry:
                continue
            # 1. positions_meta (la vue positions en dérive)
            cx.execute(
                "INSERT INTO positions_meta (ticker, status, account, wrapper) VALUES (?,?,?,?)",
                (tk, "open", (r.get("account") or "trial").strip(), (r.get("wrapper") or "CTO").strip()),
            )
            # 2. transactions : un BUY = la ligne détenue
            cx.execute(
                "INSERT INTO transactions (ticker, side, qty, price_native, fees_native, "
                "currency, fx_at_trade, trade_date, source, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (tk, "BUY", qty, px, 0.0, cur, fx, trade_date, "trial_import", "import_book"),
            )
            n_pos += 1
            # 3. thèse (optionnelle)
            conv = _f(r, "conviction")
            if conv is not None:
                cx.execute(
                    "INSERT INTO theses (ticker, opened_at, conviction, direction, "
                    "entry_price, target_partial, target_full, stop_price, notes, status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (tk, now, int(conv), (r.get("direction") or "long").strip(),
                     _f(r, "entry_price"), _f(r, "target_partial"), _f(r, "target_full"),
                     _f(r, "stop_price"), (r.get("thesis") or "").strip(), "active"),
                )
                n_thesis += 1
        if not dry:
            cx.commit()

    # 4. backfill price_history (hors transaction DB : réseau yfinance)
    if not dry and tickers:
        print(f"\nBackfill price_history ({len(tickers)} tickers, {_BACKFILL_DAYS}j)…")
        for tk in tickers:
            try:
                df = prices.ensure_price_history(tk, start, today.isoformat())
                n = len(df) if df is not None else 0
                print(f"  {tk}: {n} obs" if n else f"  [warn] {tk}: 0 obs (ticker yfinance valide ?)")
            except Exception as e:
                print(f"  [warn] {tk}: backfill échoué {type(e).__name__}: {e}")

    print(f"\n{'(DRY) ' if dry else ''}positions={n_pos}  thèses={n_thesis}  skip={n_skip}")
    if not dry:
        print("→ lance le dashboard : python -m dashboard.serve  puis http://127.0.0.1:8000/dashboard.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
