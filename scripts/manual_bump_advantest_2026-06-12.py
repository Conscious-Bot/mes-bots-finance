"""Manual bump Advantest 200 EUR — 12/06/2026 (idempotent script).

Pourquoi : Olivier a bumpé sa position 6857.T de 200 EUR via TR le 12/06
en soirée. TR n'a pas d'API live -> ingestion via CSV export manuel
(dernier 09/06). Cette transaction est ajoutée manuellement au ledger
en attendant le prochain re-export.

Convention TR ledger (post #127 rebuild) :
- price_native est stocké en EUR malgré tag currency='JPY'
- fx_at_trade=1.0 toujours (broker européen, conversion incluse côté broker)
- broker_trade_id = UUID généré (vs UUID du CSV pour ingestions auto)
- source = 'manual_bump_2026-06-12' (distingue des TR_csv_export_*)

Si Olivier re-exporte le CSV TR plus tard et que la tx broker apparaît,
la déduplication via broker_trade_id ne marche PAS (UUIDs différents).
À gérer manuellement : retirer cette tx avant re-import, OU laisser
double-comptage (visible par ratio qty broker vs ledger).

DB backup pre-INSERT obligatoire.
"""
import uuid
from datetime import UTC, datetime

from shared import prices, storage as s


def main():
    p = prices.get('6857.T')
    if p is None:
        raise RuntimeError("Live price 6857.T indispo")
    fx_jpy_eur = prices.get_fx_rate_on("JPY", "EUR", "2026-06-12")
    if not fx_jpy_eur:
        raise RuntimeError("FX JPY/EUR indispo")
    price_eur_per_share = float(p.value) * fx_jpy_eur
    qty = round(200.0 / price_eur_per_share, 6)

    trade_date = datetime.now(UTC).isoformat()
    broker_trade_id = str(uuid.uuid4())
    notes = (
        f"manual bump 200 EUR by Olivier 12/06/2026, no broker CSV yet "
        f"(live price {p.value} JPY × fx {fx_jpy_eur:.6f})"
    )

    with s.db() as cx:
        cur = cx.execute("""
            INSERT INTO transactions
            (ticker, side, qty, price_native, fees_native, currency, fx_at_trade,
             fx_is_derived, trade_date, broker_trade_id, source, is_anchor, notes,
             created_at)
            VALUES (?, 'BUY', ?, ?, 1.0, 'JPY', 1.0, 0, ?, ?, ?, 0, ?, ?)
        """, (
            '6857.T', qty, round(price_eur_per_share, 4), trade_date,
            broker_trade_id, 'manual_bump_2026-06-12', notes,
            datetime.now(UTC).isoformat(),
        ))
        if cur.rowcount != 1:
            raise RuntimeError(f"INSERT failed: rowcount={cur.rowcount}")
        cx.commit()
        print(f"✓ INSERT id={cur.lastrowid} : qty={qty} × {price_eur_per_share:.2f} EUR = {qty * price_eur_per_share:.2f} EUR")


if __name__ == "__main__":
    main()
