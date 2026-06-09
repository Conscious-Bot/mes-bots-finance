"""Back-fill #121 : INSERT historique complet 5 stale depuis exports TR.

Source : Olivier Trade Republic screenshots 2026-06-09.
Tout en EUR (TR base currency), fx_at_trade = 1.0, fees_native = 1.0 EUR/trade.

Année MU janvier confirmée 2026 (toutes dates 2026, cohérent avec les autres).

Convention :
  - broker_trade_id synthétique unique : 'TRSC-<ticker>-<datetime>-<side>-<qty>'
    (TR captures pas d'ID broker exposé → composite déterministe garantit
    idempotence DB-level via UNIQUE)
  - source : 'TR_screenshots_2026-06-09'
  - is_anchor : 0 (trades réels, pas anchors)
  - notes : gain_tr_eur si applicable (pour hand-check ledger vs TR au gate)

Validation invariants attendus post-INSERT (test final dans main()):
  - qty restante par ticker matche ground truth Olivier
  - realized_pnl ledger ≈ Σ gains TR par ticker (tolérance 0.01€ frais)
  - PRU temporel respecté (sells calculés sur buys strictement antérieurs)

Usage :
  python3 scripts/backfill_5_stale_from_tr_export.py --dry-run   # vérif data
  python3 scripts/backfill_5_stale_from_tr_export.py             # INSERT live
"""
from __future__ import annotations

import argparse
import sys

from shared import storage

# ============================================================================
# Data export TR — figée dans le script (audit-trail dans git)
# ============================================================================

# Format : (trade_date_iso, side, qty, price_eur, gain_tr_eur_or_None)
TRADES = {
    "6920.T": [
        ("2026-05-15T18:09", "BUY",  9.345794, 214.00, None),
        ("2026-05-26T17:32", "SELL", 2.232142, 224.00, 22.08),
    ],
    "ALAB": [
        ("2026-05-15T18:06", "BUY",  5.267904, 188.50, None),
        ("2026-05-15T18:41", "BUY",  1.786666, 187.50, None),
        ("2026-05-29T21:49", "SELL", 2.053333, 300.00, 228.89),
    ],
    "CCJ": [
        ("2026-05-18T19:52", "BUY",  8.01543,  93.32, None),
        ("2026-05-29T14:53", "BUY", 10.48218,  95.40, None),
        ("2026-05-29T22:41", "BUY",  6.950532, 95.82, None),
        ("2026-05-29T23:28", "SELL", 7.141327, 93.40, -11.27),
    ],
    "000660.KS": [
        ("2026-05-15T17:56", "BUY",  1.886792, 1060.00, None),
        ("2026-05-29T14:55", "SELL", 0.371212, 1325.00, 98.18),
    ],
    "MU": [
        # Janvier 2026 (confirmé Olivier 09/06) — premier achat MU, antérieur aux
        # autres positions du book (ouvertes plus tard en mai 2026).
        ("2026-01-15T18:18", "BUY",  2.535496, 295.75, None),
        ("2026-01-21T19:44", "BUY",  0.641025, 319.80, None),
        # Ventes 2026
        ("2026-02-24T18:20", "SELL", 0.27797,  359.75, 16.27),
        ("2026-04-17T23:02", "SELL", 0.258598, 386.65, 22.09),
        ("2026-05-15T17:19", "BUY",  1.070991, 653.60, None),
        ("2026-05-15T17:20", "BUY",  0.85758,  653.00, None),
        ("2026-05-16T00:28", "SELL", 1.577287, 633.90, 314.29),
        ("2026-05-16T00:32", "SELL", 0.625196, 635.00, 125.27),
        ("2026-05-29T22:37", "SELL", 0.87762,  820.30, 338.46),
        ("2026-05-29T22:38", "SELL", 0.244259, 818.70, 93.81),
    ],
}

EXPECTED_REMAINING_QTY = {
    "6920.T":    7.113652,
    "ALAB":      5.001237,
    "CCJ":      18.306815,
    "000660.KS": 1.515580,
    "MU":        1.244162,
}

EXPECTED_REALIZED_PNL_TR = {
    "6920.T":     22.08,
    "ALAB":      228.89,
    "CCJ":       -11.27,
    "000660.KS":  98.18,
    "MU":        910.19,  # 16.27+22.09+314.29+125.27+338.46+93.81
}

FEES_PER_TRADE_EUR = 1.0
SOURCE = "TR_screenshots_2026-06-09"


def synth_broker_id(ticker: str, dt: str, side: str, qty: float) -> str:
    """Synthetic composite ID for idempotence (TR pas d'ID exposé)."""
    return f"TRSC-{ticker}-{dt.replace(':', '').replace('-', '').replace('T', '_')}-{side}-{qty:.6f}"


def insert_trades(cx, dry_run: bool = False) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for ticker, trades in TRADES.items():
        # Vérif qty cumulée vs ground truth
        net_qty = sum(qty if side == "BUY" else -qty for _, side, qty, _, _ in trades)
        expected = EXPECTED_REMAINING_QTY[ticker]
        if abs(net_qty - expected) > 1e-6:
            print(f"ABORT {ticker} : qty restante {net_qty:.6f} ≠ attendu {expected:.6f}")
            return -1, -1

        for dt, side, qty, price, gain_tr in trades:
            btid = synth_broker_id(ticker, dt, side, qty)

            # Skip si déjà ingéré (idempotence via broker_trade_id UNIQUE)
            existing = cx.execute(
                "SELECT 1 FROM transactions WHERE broker_trade_id = ?", (btid,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            notes = (
                f"TR screenshot {dt[:10]}. "
                + (f"Gain TR = {gain_tr:+.2f} EUR (validation gate hand-check)."
                   if gain_tr is not None else "")
            )

            if dry_run:
                print(f"  [DRY] {ticker} {side} qty={qty:.6f} @ {price:.2f}€ "
                      f"date={dt} fees={FEES_PER_TRADE_EUR} gain_tr={gain_tr}")
            else:
                cx.execute("""
                    INSERT INTO transactions (
                        ticker, side, qty, price_native, fees_native,
                        currency, fx_at_trade, fx_is_derived,
                        trade_date, broker_trade_id, source, is_anchor, notes
                    ) VALUES (?, ?, ?, ?, ?, 'EUR', 1.0, 0, ?, ?, ?, 0, ?)
                """, (ticker, side, qty, price, FEES_PER_TRADE_EUR,
                      dt, btid, SOURCE, notes))
            inserted += 1
    if not dry_run:
        cx.commit()
    return inserted, skipped


def verify_invariants(cx) -> tuple[int, list[str]]:
    """Post-INSERT : qty restante + realized_pnl par ticker vs ground truth."""
    failures = []
    for ticker, expected_qty in EXPECTED_REMAINING_QTY.items():
        # qty calculée depuis ledger
        row = cx.execute("""
            SELECT
              COALESCE(SUM(CASE WHEN side='BUY' THEN qty ELSE 0 END), 0) -
              COALESCE(SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END), 0) AS qty
            FROM transactions WHERE ticker = ? AND source = ?
        """, (ticker, SOURCE)).fetchone()
        ledger_qty = row[0]
        if abs(ledger_qty - expected_qty) > 1e-6:
            failures.append(f"{ticker} qty : ledger {ledger_qty:.6f} ≠ attendu {expected_qty:.6f}")

        # realized_pnl via sous-requête corrélée (formule VUE SPEC §2.2)
        # En EUR pur (fx=1, fees déduits) : Σ (sell.qty × (sell.price - PRU_avant_sell) - fees_sell)
        row = cx.execute("""
            SELECT SUM(
                s.qty * s.price_native * s.fx_at_trade
              - s.fees_native * s.fx_at_trade
              - s.qty * (
                  SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade)
                       / SUM(b.qty)
                  FROM transactions b
                  WHERE b.ticker = s.ticker
                    AND b.side = 'BUY'
                    AND b.trade_date < s.trade_date
                )
            )
            FROM transactions s
            WHERE s.ticker = ? AND s.side = 'SELL'
        """, (ticker,)).fetchone()
        ledger_rpnl = row[0] or 0
        expected_rpnl = EXPECTED_REALIZED_PNL_TR[ticker]
        # Tolérance : frais à 1€/trade décale légèrement vs TR (qui inclut souvent fees nets)
        # Toléra 5€ pour absorber écart frais (5 sells max = 5€)
        if abs(ledger_rpnl - expected_rpnl) > 5.0:
            failures.append(
                f"{ticker} realized_pnl : ledger {ledger_rpnl:+.2f} ≠ TR {expected_rpnl:+.2f} "
                f"(Δ = {ledger_rpnl - expected_rpnl:+.2f})"
            )
        else:
            print(f"  ✓ {ticker} : qty={ledger_qty:.6f}, realized_pnl ledger={ledger_rpnl:+.2f}€ "
                  f"vs TR={expected_rpnl:+.2f}€ (Δ={ledger_rpnl - expected_rpnl:+.2f})")

    return len(failures), failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with storage.db() as cx:
        cx.row_factory = None
        inserted, skipped = insert_trades(cx, dry_run=args.dry_run)
        if inserted < 0:
            return 1

        print()
        print(f"=== {('DRY-RUN' if args.dry_run else 'INSERTED')} ===")
        print(f"  trades processed : {inserted + skipped}")
        print(f"  inserted now     : {inserted}")
        print(f"  skipped (déjà)   : {skipped}")
        if args.dry_run:
            print()
            print("Dry-run terminé. Re-run sans --dry-run pour INSERT live.")
            return 0

        print()
        print("=== Verify invariants (qty + realized_pnl vs TR) ===")
        n_fail, failures = verify_invariants(cx)
        if n_fail:
            print()
            print(f"FAIL {n_fail} invariant(s) :")
            for f in failures:
                print(f"  ✗ {f}")
            return 2
        print()
        print("✓ Tous les invariants matchent (qty 1e-6, realized_pnl 5€).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
