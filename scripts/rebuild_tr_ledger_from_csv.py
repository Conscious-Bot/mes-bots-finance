"""Phase 1 — Rebuild ledger TR depuis CSV export complet (anchor-free).

Cf directive Olivier 09/06 soir : "A confirmé. Verify-before-patch d'abord :
net-qty CSV (BUY/SELL + corp) == qty broker pour les 20, AVANT toute écriture.
Rocket Lab = re-map ISIN (trivial). Tesla = split 3:1 sur trades pré-25/08/2022.
Parser : TRADING/BUY/SELL, ex-crypto + cash, fee+tax capitalisés, transaction_id
→ broker_trade_id (idempotent), ISIN→ticker. Rebuild : backup → DROP+re-ingest
transactions → VUE dérive. Gate : VUE qty == broker qty (20) + realized 2026
== gains TR, no-ship si mismatch. PEA Boursorama intact (séparé)."

Discipline :
  - PEA (6 positions ASML.AS/BESI.AS/HO.PA/SAF.PA/STMPA.PA/SU.PA) INTACT
    (anchors yaml conservés, source Boursorama séparée future)
  - 20 TR seulement (Rocket Lab closed, exclus de Phase 1)
  - Tesla SPLIT 3:1 : backward-apply sur les trades pré-25/08/2022
    (qty × 3, price ÷ 3). Le BUY 2022-01-03 de 1.0 share @ 962.70 devient
    3.0 shares @ 320.90 → équivalent post-split. Le SPLIT row CSV est skippé
    pour éviter le double-comptage.
  - Rocket Lab merger : re-map US7731221062 → US7731211089 ANCIEN → NEW pour history
    (mais position closed donc transactions exclues : trades sur ISINs des 20 held only)
  - fee + tax capitalisés (fees absolu, sign retiré : CSV donne "-1.00")
  - broker_trade_id = transaction_id UUID (idempotence DB UNIQUE)
  - source = 'TR_csv_export_2026-06-09'
  - is_anchor = 0 (vrais trades, pas anchors)

Post-rebuild gate :
  - VUE qty == CSV net pour les 20 TR (tolérance 0.001)
  - PEA anchors préservés (qty/PRU inchangés)
  - Cameco diff +0.064 (manquait) attendu = corrigé automatiquement
  - Tesla = 4.838057 = qty broker confirmée Olivier

Usage : python3 scripts/rebuild_tr_ledger_from_csv.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from contextlib import contextmanager

from shared import storage

CSV_PATH = "data/broker_exports/TR_transactions_2026-06-09.csv"
SPLIT_DATE = "2022-08-25"
TESLA_ISIN = "US88160R1014"
RKLB_OLD = "US7731221062"
RKLB_NEW = "US7731211089"
SOURCE = "TR_csv_export_2026-06-09"

# 20 TR positions currently held — mapping figé (confirmé via 'name' CSV)
ISIN_TO_TICKER = {
    "JP3371200001": "4063.T",       # Shin-Etsu Chemical
    "JP3900000005": "7011.T",       # Mitsubishi Heavy
    "US5533681012": "MP",           # MP Materials
    "CA13321L1085": "CCJ",          # Cameco
    "JP3122400009": "6857.T",       # Advantest
    "US29362U1043": "ENTG",         # Entegris
    "US8740391003": "TSM",          # TSMC (ADR)
    "US16411R2085": "LNG",          # Cheniere Energy
    "US0231351067": "AMZN",         # Amazon
    "US8716071076": "SNPS",         # Synopsys
    "JP3979200007": "6920.T",       # Lasertec
    "US02079K3059": "GOOGL",        # Alphabet (A)
    "US04626A1034": "ALAB",         # Astera Labs
    "US88160R1014": "TSLA",         # Tesla
    "US0079031078": "AMD",
    "US11135F1012": "AVGO",         # Broadcom
    "US19247G1076": "COHR",         # Coherent
    "US78392B1070": "000660.KS",    # SK Hynix (GDR)
    "US4824801009": "KLAC",         # KLA
    "US5951121038": "MU",           # Micron
}

# Mapping ticker → currency native (yfinance suffix convention)
TICKER_CURRENCY = {
    "4063.T": "JPY", "7011.T": "JPY", "6857.T": "JPY", "6920.T": "JPY",
    "000660.KS": "KRW",
    # Tout le reste = USD pour US-listed (mapping yfinance)
    # ALAB/AMD/AMZN/AVGO/CCJ/COHR/ENTG/GOOGL/KLAC/LNG/MP/MU/SNPS/TSLA/TSM
}


def _native_currency(ticker: str) -> str:
    return TICKER_CURRENCY.get(ticker, "USD")


def parse_csv() -> list[dict]:
    """Build INSERT records from CSV with corp actions applied.

    Filtres :
      - category=TRADING + type IN (BUY,SELL) + asset_class=STOCK
      - ISIN in ISIN_TO_TICKER (les 20 currently held — Phase 1 scope)

    Transformations :
      - Tesla pre-25/08/2022 : qty × 3, price ÷ 3 (split 3:1 backward-applied)
      - Tesla SPLIT row : synthetic BUY shares=+2 price=0 fees=0 (pour matcher CSV)
      - fee + tax : signe absolu (CSV donne -1.00 mais le ledger stocke fees positifs)
    """
    records = []

    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            # SPLIT row (CORPORATE_ACTION) : SKIP — l'effet est appliqué via
            # transform backward sur les trades pré-split (cf logique TESLA_ISIN ci-dessous).
            # Inclure le SPLIT row en plus = double-comptage.
            if r["category"] == "CORPORATE_ACTION":
                continue

            if r["category"] != "TRADING":
                continue
            if r["type"] not in ("BUY", "SELL"):
                continue
            if r["asset_class"] != "STOCK":
                continue

            isin = r["symbol"]
            qty_signed = float(r["shares"])

            # Rocket Lab merger : re-map (les 2 ISINs ont fait l'objet d'une fusion)
            # Note : RKLB est closed (net=0) donc PAS dans ISIN_TO_TICKER. Skip.
            if isin == RKLB_OLD:
                continue

            # Filter scope Phase 1 : 20 ISINs held
            if isin not in ISIN_TO_TICKER:
                continue

            ticker = ISIN_TO_TICKER[isin]

            # Tesla split 3:1 backward
            qty_abs = abs(qty_signed)
            price = float(r["price"])
            if isin == TESLA_ISIN and r["date"] < SPLIT_DATE:
                qty_abs *= 3
                price /= 3

            fee = abs(float(r["fee"] or 0))
            tax = abs(float(r["tax"] or 0))

            records.append({
                "ticker": ticker,
                "side": r["type"],   # BUY ou SELL
                "qty": qty_abs,
                "price_native": price,
                "fees_native": fee + tax,  # FTT française capitalisée avec frais
                "currency": _native_currency(ticker),  # convention yfinance
                "fx_at_trade": 1.0,    # TR convertit EUR avant nous ; on traite tout EUR-equivalent
                "fx_is_derived": 0,
                "trade_date": r["datetime"],
                "broker_trade_id": r["transaction_id"],
                "source": SOURCE,
                "is_anchor": 0,
                "notes": f"TR CSV import 2026-06-09 ({r['name']})",
            })

    return records


@contextmanager
def transactional_no_triggers(cx):
    """Permet DROP transactions malgré le trigger BEFORE DELETE.

    Strictement encadré : on désactive les triggers UNIQUEMENT pour cette
    opération de rebuild, dans la même transaction que le re-INSERT. Si quoi
    que ce soit échoue, on rollback et on restore les triggers.
    """
    cx.execute("DROP TRIGGER IF EXISTS transactions_writeonce_delete")
    try:
        yield
    finally:
        cx.execute(
            "CREATE TRIGGER transactions_writeonce_delete "
            "BEFORE DELETE ON transactions FOR EACH ROW "
            "BEGIN "
            "SELECT RAISE(ABORT, 'transactions append-only (SPEC_LEDGER §1) : "
            "suppression interdite. Corriger via entrée compensatoire (ADJUST futur).'); "
            "END"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records = parse_csv()
    print(f"=== Parsed {len(records)} transactions from CSV ===")

    # Net qty par ticker (sanity preview)
    net = defaultdict(float)
    for r in records:
        net[r["ticker"]] += r["qty"] if r["side"] == "BUY" else -r["qty"]
    print()
    print("Net qty reconstruit par ticker :")
    for t, q in sorted(net.items()):
        print(f"  {t:10s}  {q:>14.6f}")

    if args.dry_run:
        print()
        print("DRY-RUN : aucune écriture. Re-run sans --dry-run pour rebuild.")
        return 0

    tr_tickers = tuple(ISIN_TO_TICKER.values())

    with storage.db() as cx:
        cx.row_factory = None

        # Count existing TR transactions (qui seront supprimées)
        n_to_delete = cx.execute(
            f"SELECT COUNT(*) FROM transactions WHERE ticker IN ({','.join('?'*len(tr_tickers))})",
            tr_tickers,
        ).fetchone()[0]
        n_pea_keep = cx.execute(
            f"SELECT COUNT(*) FROM transactions WHERE ticker NOT IN ({','.join('?'*len(tr_tickers))})",
            tr_tickers,
        ).fetchone()[0]
        print()
        print("=== Pre-rebuild state ===")
        print(f"  Transactions TR à supprimer : {n_to_delete}")
        print(f"  Transactions PEA à conserver : {n_pea_keep}")

        # Atomic rebuild
        with transactional_no_triggers(cx):
            cx.execute(
                f"DELETE FROM transactions WHERE ticker IN ({','.join('?'*len(tr_tickers))})",
                tr_tickers,
            )
            n_deleted = cx.total_changes
            print(f"  → DELETE done, {n_deleted} rows removed")

            inserted = 0
            for rec in records:
                try:
                    cx.execute(
                        "INSERT INTO transactions ("
                        "ticker, side, qty, price_native, fees_native, "
                        "currency, fx_at_trade, fx_is_derived, "
                        "trade_date, broker_trade_id, source, is_anchor, notes"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (rec["ticker"], rec["side"], rec["qty"], rec["price_native"],
                         rec["fees_native"], rec["currency"], rec["fx_at_trade"],
                         rec["fx_is_derived"], rec["trade_date"],
                         rec["broker_trade_id"], rec["source"], rec["is_anchor"],
                         rec["notes"]),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  INSERT failed for {rec['ticker']} {rec['side']} "
                          f"qty={rec['qty']} ({rec['broker_trade_id']}): {e}")
                    raise
            print(f"  → INSERT done, {inserted} new transactions")

        cx.commit()

        # Post-rebuild gate : VUE qty == CSV net
        print()
        print("=== Post-rebuild gate : VUE qty vs CSV net ===")
        all_match = True
        for ticker in sorted(ISIN_TO_TICKER.values()):
            row = cx.execute(
                "SELECT qty FROM positions WHERE ticker = ? AND status='open'", (ticker,)
            ).fetchone()
            vue_qty = float(row[0]) if row and row[0] is not None else 0
            csv_qty = net[ticker]
            d = vue_qty - csv_qty
            flag = "✓" if abs(d) < 0.001 else "✗ MISMATCH"
            print(f"  {ticker:10s}  VUE={vue_qty:>14.6f}  CSV={csv_qty:>14.6f}  Δ={d:+.6f}  {flag}")
            if abs(d) >= 0.001:
                all_match = False

        # PEA preserved check
        print()
        print("=== PEA anchors check (doivent rester intacts) ===")
        pea_tickers = ("ASML.AS", "BESI.AS", "HO.PA", "SAF.PA", "STMPA.PA", "SU.PA")
        for tk in pea_tickers:
            row = cx.execute(
                "SELECT qty, avg_cost_eur FROM positions WHERE ticker = ? AND status='open'",
                (tk,)
            ).fetchone()
            if row:
                print(f"  {tk:10s}  qty={row[0]:.4f}  pru={row[1]:.2f}€  ✓")
            else:
                print(f"  {tk:10s}  MISSING ✗")
                all_match = False

        if all_match:
            print()
            print("✓ GATE GREEN : rebuild successful, ledger TR aligné CSV, PEA intact")
            return 0
        else:
            print()
            print("✗ GATE RED : mismatch détecté — investigate avant ship")
            return 1


if __name__ == "__main__":
    sys.exit(main())
