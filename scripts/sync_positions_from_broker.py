"""Sync positions table from config/broker_positions.yaml (source canonique).

Pattern declaratif L17 : le YAML est la verite. La table positions = cache
derive. Aucun autre code ne doit ecrire dans les fields user-input (qty,
avg_cost_eur, account, status). Seul ce script y touche.

Distinction stricte des fields positions :
  USER-INPUT (broker source, write par CE script SEUL) :
    - ticker, qty, avg_cost_eur, account, status, opened_at, notes
  MARKET-DERIVED (yfinance source, write par reconcile_positions_prices.py) :
    - last_price_native, last_price_currency, price_asof, price_source,
      fx_rate_to_eur, fx_asof, fx_source

Ces deux ecrivains sont DISJOINTS -- pas de race condition, pas d'override.

Usage :
    python3 scripts/sync_positions_from_broker.py [--dry-run] [--verify]

  --dry-run : montre les diff sans appliquer
  --verify  : verifie post-sync que dashboard P&L == yaml snapshot

Idempotent : re-run = no-op si DB deja sync.

Cf [[L26]] (a graver) : "broker positions = YAML declaratif, DB = cache,
jamais write user-input fields hors de ce script."
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("sync_broker")

_YAML_PATH = _REPO_ROOT / "config" / "broker_positions.yaml"


def load_broker_yaml(path: Path | None = None) -> dict:
    """Charge le YAML canonique. Raise si malformed."""
    p = path or _YAML_PATH
    if not p.exists():
        raise FileNotFoundError(f"broker_positions.yaml introuvable à {p}")
    with p.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "accounts" not in data:
        raise ValueError("broker_positions.yaml malformed (missing 'accounts')")
    return data


def _derive_qty_and_avg_cost(value_eur: float, pnl_pct: float,
                              last_price_native: float | None,
                              fx_rate_to_eur: float | None) -> tuple[float | None, float | None]:
    """Pour les TR positions sans qty explicite : derive qty + avg_cost_eur.

    qty = value_eur / (last_native × fx_rate_to_eur)
    cost_basis_eur = value_eur / (1 + pnl_pct/100)
    avg_cost_eur = cost_basis_eur / qty

    Returns (qty, avg_cost_eur) ou (None, None) si market data manquant.
    """
    if not last_price_native or not fx_rate_to_eur:
        return None, None
    if last_price_native <= 0 or fx_rate_to_eur <= 0:
        return None, None
    qty = value_eur / (last_price_native * fx_rate_to_eur)
    cost_basis = value_eur / (1 + pnl_pct / 100.0)
    avg_cost_eur = cost_basis / qty
    return qty, avg_cost_eur


def _fetch_market_data_for_new_ticker(ticker: str) -> dict | None:
    """Pour un nouveau ticker (pas en DB) : fetch live market data via gateway.

    Retourne dict {last_price_native, last_price_currency, fx_rate_to_eur, price_asof}
    ou None si fetch fail.
    """
    try:
        from shared import prices
        from shared.prices import get_currency_for_ticker
        currency = get_currency_for_ticker(ticker)
        price_native = prices.get_current_price(ticker)
        if price_native is None:
            return None
        fx = 1.0 if currency == "EUR" else prices.get_fx_rate(currency, "EUR")
        if fx is None:
            return None
        from datetime import UTC, datetime
        return {
            "last_price_native": price_native,
            "last_price_currency": currency,
            "fx_rate_to_eur": fx,
            "price_asof": datetime.now(UTC).isoformat(),
            "price_source": "sync_broker_insert",
            "fx_asof": datetime.now(UTC).isoformat(),
            "fx_source": "sync_broker_insert",
        }
    except Exception as e:
        log.warning(f"_fetch_market_data_for_new_ticker {ticker}: {e}")
        return None


def sync(dry_run: bool = False) -> dict:
    """Applique le YAML a la table positions. UPDATE existants + INSERT nouveaux."""
    from shared import storage
    yaml_data = load_broker_yaml()
    summary = {"updated": [], "inserted": [], "skipped": [], "errors": []}

    with storage.db() as cx:
        cx.row_factory = None
        for account_name, acct_data in yaml_data["accounts"].items():
            for pos in acct_data["positions"]:
                ticker = pos["ticker"]
                row = cx.execute(
                    "SELECT id, last_price_native, fx_rate_to_eur FROM positions "
                    "WHERE ticker=? AND status='open'", (ticker,)
                ).fetchone()

                is_new = row is None
                if is_new:
                    # Nouveau ticker (ex. achat recent) : fetch market live pour INSERT
                    market = _fetch_market_data_for_new_ticker(ticker)
                    if market is None:
                        summary["errors"].append(
                            f"{ticker}: new ticker, fetch market data failed (gateway prices.get/fx). "
                            "Reessayer apres le prochain cron reconcile_positions_prices."
                        )
                        continue
                    lpn = market["last_price_native"]
                    fx_now = market["fx_rate_to_eur"]
                    pos_id = None  # INSERT a venir
                else:
                    pos_id, lpn, fx_now = row

                # Resolve qty + avg_cost_eur (UPDATE ou INSERT)
                if "qty" in pos and "avg_cost_eur" in pos:
                    qty = float(pos["qty"])
                    avg_cost_eur = float(pos["avg_cost_eur"])
                    source = "yaml_direct"
                elif "value_eur_snapshot" in pos and "pnl_pct_snapshot" in pos:
                    qty, avg_cost_eur = _derive_qty_and_avg_cost(
                        float(pos["value_eur_snapshot"]),
                        float(pos["pnl_pct_snapshot"]),
                        lpn, fx_now,
                    )
                    source = "yaml_derived"
                    if qty is None:
                        summary["errors"].append(f"{ticker}: cannot derive qty (no market data)")
                        continue
                else:
                    summary["errors"].append(
                        f"{ticker}: yaml entry incomplete (need qty+avg_cost OR value+pnl)"
                    )
                    continue

                if dry_run:
                    pass  # skip write
                elif is_new:
                    # INSERT new position avec market data fetched + user-input fields
                    from datetime import UTC, datetime
                    cx.execute(
                        "INSERT INTO positions (ticker, qty, avg_cost, avg_cost_eur, "
                        "  avg_cost_native, fx_at_purchase, avg_cost_currency, "
                        "  account, status, opened_at, notes, "
                        "  last_price_native, last_price_currency, price_asof, price_source, "
                        "  fx_rate_to_eur, fx_asof, fx_source) "
                        "VALUES (?, ?, ?, ?, ?, 1.0, 'EUR', ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            ticker, qty, avg_cost_eur, avg_cost_eur,
                            avg_cost_eur, account_name,
                            datetime.now(UTC).isoformat(),
                            f"sync_from_broker_yaml {datetime.now(UTC).date().isoformat()}",
                            market["last_price_native"], market["last_price_currency"],
                            market["price_asof"], market["price_source"],
                            market["fx_rate_to_eur"], market["fx_asof"], market["fx_source"],
                        ),
                    )
                    summary["inserted"].append({
                        "ticker": ticker, "account": account_name, "source": source,
                        "qty": round(qty, 6), "avg_cost_eur": round(avg_cost_eur, 4),
                    })
                else:
                    cx.execute(
                        "UPDATE positions SET "
                        "  qty=?, avg_cost_eur=?, avg_cost_native=?, "
                        "  fx_at_purchase=1.0, avg_cost_currency='EUR', "
                        "  account=? "
                        "WHERE id=?",
                        (qty, avg_cost_eur, avg_cost_eur, account_name, pos_id),
                    )
                    summary["updated"].append({
                        "ticker": ticker, "account": account_name, "source": source,
                        "qty": round(qty, 6), "avg_cost_eur": round(avg_cost_eur, 4),
                    })

        # MARK_CLOSED : tickers en DB status=open mais ABSENTS du YAML
        yaml_tickers = {p["ticker"] for acct in yaml_data["accounts"].values() for p in acct["positions"]}
        db_open = cx.execute("SELECT id, ticker FROM positions WHERE status='open' AND qty > 0").fetchall()
        for pid, tk in db_open:
            if tk not in yaml_tickers:
                if not dry_run:
                    from datetime import UTC, datetime
                    cx.execute(
                        "UPDATE positions SET status='closed', qty=0, "
                        "  last_updated=? WHERE id=?",
                        (datetime.now(UTC).isoformat(), pid),
                    )
                summary["skipped"].append({"ticker": tk, "action": "closed (absent du YAML)"})

        if not dry_run:
            cx.commit()
    return summary


def verify() -> dict:
    """Post-sync : verifie que pour chaque ticker du YAML, le P&L dashboard
    derive (qty * last_native * fx / cost_basis_eur - 1) == yaml pnl_snapshot
    a +/- 0.5%.
    """
    from shared import storage
    yaml_data = load_broker_yaml()
    mismatches = []
    matches = 0
    with storage.db() as cx:
        cx.row_factory = None
        for acct_name, acct_data in yaml_data["accounts"].items():
            for pos in acct_data["positions"]:
                tk = pos["ticker"]
                target_pnl_pct = pos.get("pnl_pct_snapshot")
                if target_pnl_pct is None:
                    continue  # skip si pas de snapshot
                row = cx.execute(
                    "SELECT qty, avg_cost_eur, last_price_native, fx_rate_to_eur "
                    "FROM positions WHERE ticker=? AND status='open'", (tk,)
                ).fetchone()
                if not row:
                    mismatches.append({"ticker": tk, "issue": "no DB row"})
                    continue
                qty, ace, lpn, fx = row
                if not all([qty, ace, lpn, fx]):
                    mismatches.append({"ticker": tk, "issue": "incomplete data"})
                    continue
                value_eur = qty * lpn * fx
                cost = qty * ace
                if cost == 0:
                    mismatches.append({"ticker": tk, "issue": "zero cost"})
                    continue
                actual_pnl = (value_eur / cost - 1) * 100
                if abs(actual_pnl - target_pnl_pct) > 0.5:
                    mismatches.append({
                        "ticker": tk, "target": target_pnl_pct,
                        "actual": round(actual_pnl, 2),
                        "delta": round(actual_pnl - target_pnl_pct, 2),
                    })
                else:
                    matches += 1
    return {"matches": matches, "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        v = verify()
        print(f"VERIFY : {v['matches']} match, {len(v['mismatches'])} mismatches")
        for m in v["mismatches"]:
            print(f"  {m}")
        return 0 if not v["mismatches"] else 1

    summary = sync(dry_run=args.dry_run)
    action = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"{action} : {len(summary['updated'])} positions sync, "
          f"{len(summary['errors'])} errors")
    for u in summary["updated"]:
        print(f"  + {u['ticker']:<12} {u['account']:>4} qty={u['qty']:>10.4f} "
              f"avg_cost_eur={u['avg_cost_eur']:>10.4f} ({u['source']})")
    for e in summary["errors"]:
        print(f"  ! {e}")

    # Auto-verify if applied
    if not args.dry_run:
        print()
        v = verify()
        print(f"VERIFY post-sync : {v['matches']} match / {len(v['mismatches'])} mismatches")
        if v["mismatches"]:
            print("WARN : mismatches detected. Verifier broker_positions.yaml.")
            for m in v["mismatches"]:
                print(f"  {m}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
