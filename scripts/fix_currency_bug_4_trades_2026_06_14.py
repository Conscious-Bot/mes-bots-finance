"""Fix currency bug 4 trades (id 198-201, broker import 2026-06-12 14:28:30).

Bug : `price_native` stored in EUR but `currency='USD'` + `fx_at_trade=1.0`.
EUR debited correct (= what TR actually charged), mais projection USD cassée,
PMP USD faux, P&L attribution mélange dimensions.

Cure : 4 tx side='ADJUST' avec override price_native + fx_at_trade (cf
SPEC_LEDGER §1 "extensible 'ADJUST' (futur)"). Pas de UPDATE (trigger
RAISE), pas de reversal-BUY (PMP path-dependent pollution interdite par
memory partial_close_handler_missing).

`shared/ledger_pmp.py:compute_pmp_realized` modifie pour lire ADJUST avant
iteration BUYs/SELLs (commit memo dans diff). PMP recalculated correctly.

Idempotent : check si ADJUST tx déjà inserted via source='manual_currency_correction_2026_06_14'.

Usage :
    python3 scripts/fix_currency_bug_4_trades_2026_06_14.py [--apply]

Sans --apply : dry-run, montre les corrections proposées.
Avec --apply : INSERT les 4 ADJUST tx.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "bot.db"

# Fx USD→EUR @ 2026-06-12T14:28:30 (exact match dans fx_history)
FX_USD_TO_EUR = 0.864

# Les 4 tx avec leur EUR débité calculé (= ce que TR a réellement débité)
# Les stored values sont price_native (en EUR but tagged USD) × 1.0 × qty
TRADES = [
    {"target_id": 198, "ticker": "ALAB",  "qty": 1.242, "stored_price": 319.65},
    {"target_id": 199, "ticker": "GOOGL", "qty": 1.0,   "stored_price": 312.00},
    {"target_id": 200, "ticker": "AMD",   "qty": 0.741, "stored_price": 445.34},
    {"target_id": 201, "ticker": "AMZN",  "qty": 1.61,  "stored_price": 204.97},
]

SOURCE_TAG = "manual_currency_correction_2026_06_14"


def compute_corrected(t: dict) -> dict:
    """EUR debited = qty × stored_price × 1.0 (current wrong state).
    Corrected : qty × USD_price × FX = EUR debited (same).
    Donc USD_price = stored_price / FX (EUR debited / qty / FX).
    fx_at_trade = FX_USD_TO_EUR.
    """
    eur_debited = t["qty"] * t["stored_price"] * 1.0
    corrected_usd_price = t["stored_price"] / FX_USD_TO_EUR
    return {
        "eur_debited": eur_debited,
        "corrected_price_native": round(corrected_usd_price, 4),
        "corrected_fx": FX_USD_TO_EUR,
    }


def already_applied(conn: sqlite3.Connection) -> int:
    """Returns count of ADJUST tx with our SOURCE_TAG."""
    cur = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE side='ADJUST' AND source=?",
        (SOURCE_TAG,),
    )
    return cur.fetchone()[0]


def insert_adjust(conn: sqlite3.Connection, t: dict, corrected: dict) -> int:
    """Insert ADJUST tx referencing target_tx_id via notes JSON."""
    notes = json.dumps({
        "target_tx_id": t["target_id"],
        "reason": "currency_bug_2026_06_12_trades_198_to_201",
        "original_price_native": t["stored_price"],
        "original_fx_at_trade": 1.0,
        "fx_source": "fx_history_USD_EUR_at_2026-06-12T14:28:30",
    })
    cur = conn.execute(
        """INSERT INTO transactions
           (ticker, side, qty, price_native, fees_native, currency, fx_at_trade,
            fx_is_derived, trade_date, broker_trade_id, source, is_anchor, notes)
           VALUES (?, 'ADJUST', ?, ?, 0, 'USD', ?, 0,
                   '2026-06-14T11:00:00+00:00', NULL, ?, 0, ?)""",
        (t["ticker"], t["qty"], corrected["corrected_price_native"],
         corrected["corrected_fx"], SOURCE_TAG, notes),
    )
    return cur.lastrowid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="INSERT les 4 ADJUST tx")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB))
    try:
        existing = already_applied(conn)
        if existing > 0:
            print(f"⚠ {existing} ADJUST tx avec source={SOURCE_TAG!r} déjà présentes. Idempotent skip.")
            return

        print("═ Currency bug cure — 4 tx (id 198-201) ═")
        print(f"FX USD→EUR @ 2026-06-12T14:28:30 = {FX_USD_TO_EUR}")
        print()
        print(f"{'id':>4} {'ticker':<6} {'qty':>6} {'p_stored':>10} {'EUR_debited':>11} {'true_USD_price':>14} {'new_fx':>8}")
        print("─" * 75)
        for t in TRADES:
            c = compute_corrected(t)
            print(f"  {t['target_id']:>3} {t['ticker']:<6} {t['qty']:>6.3f} "
                  f"{t['stored_price']:>10.2f} {c['eur_debited']:>11.2f} "
                  f"{c['corrected_price_native']:>14.4f} {c['corrected_fx']:>8.4f}")
        print()

        if not args.apply:
            print("Dry-run. Re-run avec --apply pour INSERT.")
            return

        print("═ Inserting 4 ADJUST tx ═")
        for t in TRADES:
            c = compute_corrected(t)
            new_id = insert_adjust(conn, t, c)
            print(f"  ADJUST tx id={new_id} target_id={t['target_id']} ({t['ticker']})")
        conn.commit()
        print("\n✓ 4 ADJUST tx inserted. PMP recalcule via ledger_pmp.compute_pmp_realized.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
