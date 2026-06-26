"""Template canonique pour scripts exec trade manuel via VM ssh+python.

Pattern obligatoire pour TOUT trade manuel — utilise le helper
`shared.storage.insert_decision_with_cf` qui INSERT atomiquement
decision + decision_counterfactual (ferme dette rule #7, cf memory
[[manual-exec-must-create-cf]]).

USAGE :
  1. Copier ce fichier vers /tmp/exec_<action>_<date>.py
  2. Remplir les 4 sections marquees `# >>> ICI <<<`
  3. scp vers VM : scp /tmp/exec_<...>.py presage@37.27.247.126:/tmp/
  4. Exec sur VM : ssh presage@37.27.247.126 "/home/presage/mes-bots-finance/venv/bin/python3 /tmp/exec_<...>.py"
  5. Sync VM -> Mac : bash scripts/sync_db_from_hetzner.sh
"""

from __future__ import annotations

import os
import sqlite3
import sys

# Sur la VM, le repo est en /home/presage/mes-bots-finance.
sys.path.insert(0, "/home/presage/mes-bots-finance")

from shared import storage

# >>> ICI <<< — DB path (VM)
storage.DB_PATH = "/home/presage/mes-bots-finance/data/bot.db"

if not os.path.exists(storage.DB_PATH):
    print(f"ERROR: DB not found {storage.DB_PATH}", file=sys.stderr)
    sys.exit(1)

# >>> ICI <<< — Trade params (a remplir depuis confirmation broker)
TICKER       = "TICKER.PA"         # symbole tel que dans theses.ticker
SIDE         = "BUY"               # 'BUY' ou 'SELL'
DECISION_TYPE = "entry"            # 'entry' | 'scale_in' | 'partial_exit' | 'full_exit'
QTY          = 0.0                 # quantite executee
PRICE_NATIVE = 0.0                 # prix par share dans currency native
CURRENCY     = "EUR"               # 'EUR' | 'USD' | 'JPY' | 'KRW'
FX_AT_TRADE  = 1.0                 # 1.0 si EUR, sinon fx du jour
SOURCE       = "manual_<action>_<broker>_2026-XX-XX"
NOTES        = ""                  # description courte broker-side

# >>> ICI <<< — [STRUCTURED] reasoning (3 champs obligatoires)
REASONING = (
    f"[STRUCTURED] these: {TICKER} cX <action> "
    f"(raison structural — pas juste 'prix monte'). "
    f"| invalidation: triggers existants OR nouveau trigger structural "
    f"| conviction: X"
)


def main():
    cx = sqlite3.connect(storage.DB_PATH)
    cx.execute("BEGIN")
    try:
        # 1. Recuperer these active + qty_before
        row = cx.execute(
            "SELECT id, conviction FROM theses WHERE ticker=? AND status='active'",
            (TICKER,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"No active thesis for {TICKER}")
        thesis_id, conviction = row

        qty_before = cx.execute(
            "SELECT qty FROM positions WHERE ticker=?", (TICKER,)
        ).fetchone()
        qty_before = qty_before[0] if qty_before else 0.0

        # 2. INSERT transaction (append-only ledger)
        cx.execute(
            "INSERT INTO transactions (ticker, side, qty, price_native, fees_native, "
            "currency, fx_at_trade, fx_is_derived, trade_date, source, is_anchor, notes) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, 0, datetime('now'), ?, 0, ?)",
            (TICKER, SIDE, QTY, PRICE_NATIVE, CURRENCY, FX_AT_TRADE, SOURCE, NOTES),
        )
        tx_id = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"tx#{tx_id} {SIDE} {QTY} sh @ {PRICE_NATIVE} {CURRENCY}")

        # 3. Helper canonique : INSERT decision + CF atomiquement
        dec_id, cf_id = storage.insert_decision_with_cf(
            ticker=TICKER,
            decision_type=DECISION_TYPE,
            reasoning=REASONING,
            thesis_id=thesis_id,
            conviction=conviction,
            price_native=PRICE_NATIVE,
            qty_before=qty_before,
            currency=CURRENCY,
            price_eur=PRICE_NATIVE * FX_AT_TRADE if CURRENCY != "EUR" else PRICE_NATIVE,
            conn=cx,  # IMPORTANT : embarque dans la meme tx
        )
        print(f"decision#{dec_id}  CF#{cf_id}  (thesis_id={thesis_id})")

        cx.commit()
        print("=== COMMIT ===")
    except Exception as e:
        cx.rollback()
        print(f"ROLLBACK: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cx.close()


if __name__ == "__main__":
    main()
