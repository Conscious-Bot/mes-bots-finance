"""Import 21 legacy positions (6 PEA + 15 TR executed) with current market value as cost basis.

Cost basis approach: entry_price = current market price in EUR.
This means PnL=0 today (forward-tracking baseline, honest about no real entry data).
qty = eur_invested / price_eur

Currency handled via yfinance ticker suffix:
  .PA .AS .SW -> EUR
  .T -> JPY
  .KS -> KRW
  .HK -> HKD
  .L -> GBP
  no suffix -> USD

FX rates fetched once via yfinance pairs (EURUSD=X etc.).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf

from shared import positions as positions_mod, storage

# (ticker, account, eur_invested)
LEGACY_POSITIONS = [
    # PEA — 6 positions
    ("ASML.AS",  "PEA", 3930),
    ("STMPA.PA", "PEA", 2205),
    ("SU.PA",    "PEA", 1581),
    ("BESI.AS",  "PEA", 1567),
    ("HO.PA",    "PEA", 1554),
    ("SAF.PA",   "PEA", 547),
    # TR executed — 15 positions
    ("4063.T",    "TR", 4500),
    ("TSM",       "TR", 4000),
    ("SNPS",      "TR", 3000),
    ("7011.T",    "TR", 2500),  # topup +1000 planned W1, will be added when executed
    ("000660.KS", "TR", 2000),
    ("KLAC",      "TR", 2000),
    ("6920.T",    "TR", 2000),
    ("MRVL",      "TR", 2000),
    ("AVGO",      "TR", 1500),
    ("TER",       "TR", 1500),
    ("ALAB",      "TR", 1500),
    ("COHR",      "TR", 1500),
    ("AMD",       "TR", 1500),
    ("GOOGL",     "TR", 1500),
    ("TSLA",      "TR", 1000),
]


def ticker_currency(ticker: str) -> str:
    if ticker.endswith((".PA", ".AS", ".SW")):
        return "EUR"
    if ticker.endswith(".T"):
        return "JPY"
    if ticker.endswith(".KS"):
        return "KRW"
    if ticker.endswith(".HK"):
        return "HKD"
    if ticker.endswith(".L"):
        return "GBP"
    return "USD"


def fetch_fx_rates() -> dict:
    """EUR per native: e.g. fx['USD'] = 1/EURUSD = how many EUR per 1 USD."""
    pairs = {
        "USD": "EURUSD=X",
        "JPY": "EURJPY=X",
        "KRW": "EURKRW=X",
        "HKD": "EURHKD=X",
        "GBP": "EURGBP=X",
    }
    rates = {"EUR": 1.0}
    for currency, pair in pairs.items():
        try:
            hist = yf.Ticker(pair).history(period="1d")
            if not hist.empty:
                eur_per_native_inverse = hist["Close"].iloc[-1]
                rates[currency] = 1.0 / eur_per_native_inverse  # 1 native = X EUR
            else:
                print(f"  WARN: FX {pair} empty, using 1.0 fallback (POISON DATA)")
                rates[currency] = 1.0
        except Exception as e:
            print(f"  WARN: FX {pair} error {e}, using 1.0 fallback")
            rates[currency] = 1.0
    return rates


def fetch_price_eur(ticker: str, fx_rates: dict) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        if hist.empty:
            return None
        price_native = float(hist["Close"].iloc[-1])
        currency = ticker_currency(ticker)
        return price_native * fx_rates[currency]
    except Exception as e:
        print(f"  ERROR fetching {ticker}: {e}")
        return None


def main():
    print("Fetching FX rates (EUR per native currency)...")
    fx = fetch_fx_rates()
    print(f"  USD: 1 USD = {fx['USD']:.4f} EUR")
    print(f"  JPY: 1 JPY = {fx['JPY']:.6f} EUR")
    print(f"  KRW: 1 KRW = {fx['KRW']:.6f} EUR")
    print(f"  HKD: 1 HKD = {fx['HKD']:.4f} EUR")
    print(f"  GBP: 1 GBP = {fx['GBP']:.4f} EUR")
    print()

    note_tag = "legacy_import_2026_05_15"

    inserted = 0
    skipped = 0
    for ticker, account, eur_invested in LEGACY_POSITIONS:
        price_eur = fetch_price_eur(ticker, fx)
        if price_eur is None or price_eur <= 0:
            print(f"  SKIP {ticker:12s} (no price)")
            skipped += 1
            continue

        qty = eur_invested / price_eur
        notes = f"{note_tag} | account={account} | eur_invested={eur_invested}"

        positions_mod.add_buy(ticker, qty, price_eur, notes=notes)
        # add_buy returns {ticker, ...} but not position_id; UPDATE by ticker + most recent
        with storage.db() as cx:
            cx.execute(
                "UPDATE positions SET account=? WHERE id=(SELECT MAX(id) FROM positions WHERE ticker=? AND status='open')",
                (account, ticker),
            )

        print(f"  ADD  {ticker:12s} {account:4s}  €{eur_invested:>5.0f}  qty={qty:>9.3f}  px_eur={price_eur:>8.2f}")
        inserted += 1

    print(f"\nDone: inserted={inserted} skipped={skipped}")

    # Summary
    with storage.db() as cx:
        for r in cx.execute(
            """SELECT account, COUNT(*) AS n, SUM(qty*avg_cost) AS eur
               FROM positions WHERE status='open' AND notes LIKE ?
               GROUP BY account""",
            (f"%{note_tag}%",),
        ):
            print(f"  {r['account']:6s}: n={r['n']:2d}  total_eur=€{r['eur']:>7.0f}")


if __name__ == "__main__":
    main()
