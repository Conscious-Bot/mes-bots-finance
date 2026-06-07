"""Reconciliation job unique des positions via prices.get() (Axe 3 1er geste).

Spec QUALITY_BAR Axe 3 : "1 job de reconciliation unique via prices.get().
Tout lit cet etat."

UNIQUE point d'entree pour rafraichir last_price_native + price_asof + FX.
- Lit positions ouvertes
- Pour chaque ticker : call shared.prices.get_current_price -> persiste price_history (M1 wire deja en place)
- Si non-EUR : call shared.prices.get_fx_rate -> persiste fx_history
- Update positions.last_price_native / price_asof / price_source / fx_rate_to_eur / fx_asof / fx_source
  AVEC les latest observations append-only (via storage.get_latest_price)

Idempotence : si pas de nouvelle observation -> les colonnes restent
sur leur derniere valeur (asof reflet la fraicheur reelle).

Run :
  python3 scripts/reconcile_positions_prices.py

Cron suggere : every 15min business hours OU on-demand depuis dashboard.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("reconcile_positions")


def reconcile_one(ticker: str) -> dict:
    """Fetch + persist + return latest observation pour 1 ticker.

    Returns dict {ticker, price_native, currency, price_asof, fx_rate, fx_asof}
    avec None si fetch fail (fail-closed L15 surface).
    """
    from shared import storage
    from shared.prices import get_currency_for_ticker, get_current_price, get_fx_rate

    out = {
        "ticker": ticker, "price_native": None, "currency": None,
        "price_asof": None, "price_source": None,
        "fx_rate_to_eur": None, "fx_asof": None, "fx_source": None,
        "fetch_ok": False,
    }

    # 1. Fetch live price (persiste price_history via hook M1 deja en place)
    price = get_current_price(ticker)
    if price is None:
        log.warning(f"  {ticker}: price fetch FAILED (fail-closed L15 columns NOT updated)")
        return out
    currency = get_currency_for_ticker(ticker)

    # 2. Latest observation depuis price_history (le hook M1 vient d'inserer ca)
    latest_px = storage.get_latest_price(ticker)
    if latest_px is None:
        log.warning(f"  {ticker}: get_latest_price retourne None (DB write fail?)")
        return out

    out["price_native"] = latest_px["price_native"]
    out["currency"] = latest_px["currency"]
    out["price_asof"] = latest_px["asof"]
    out["price_source"] = latest_px["source"]

    # 3. Fetch FX si non-EUR (persiste fx_history via hook M1)
    if currency != "EUR":
        fx = get_fx_rate(currency, "EUR")
        if fx is None:
            log.warning(f"  {ticker}: FX {currency}->EUR FAILED")
        else:
            latest_fx = storage.get_latest_fx_rate(currency, "EUR")
            if latest_fx:
                out["fx_rate_to_eur"] = latest_fx["rate"]
                out["fx_asof"] = latest_fx["asof"]
                out["fx_source"] = latest_fx["source"]
    else:
        # EUR identity
        out["fx_rate_to_eur"] = 1.0
        out["fx_asof"] = latest_px["asof"]  # synthetic identity
        out["fx_source"] = "identity"

    out["fetch_ok"] = True
    return out


def update_position_columns(position_id: int, obs: dict) -> bool:
    """Update positions row avec latest observation. Idempotent."""
    from shared import storage
    if not obs.get("fetch_ok"):
        return False
    try:
        with storage.db() as cx:
            cx.execute(
                "UPDATE positions SET "
                "  last_price_native = ?, last_price_currency = ?, "
                "  price_asof = ?, price_source = ?, "
                "  fx_rate_to_eur = ?, fx_asof = ?, fx_source = ?, "
                "  last_updated = ? "
                "WHERE id = ?",
                (
                    obs["price_native"], obs["currency"],
                    obs["price_asof"], obs["price_source"],
                    obs["fx_rate_to_eur"], obs["fx_asof"], obs["fx_source"],
                    datetime.now(UTC).isoformat(),
                    position_id,
                ),
            )
            return True
    except Exception as e:
        log.warning(f"update_position_columns pid={position_id} failed: {e}")
        return False


def main() -> int:
    from shared import storage

    # Lit positions ouvertes
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT id, ticker, qty FROM positions WHERE status='open' AND qty > 0"
        ).fetchall()

    if not rows:
        log.info("Aucune position ouverte, rien a reconcilier")
        return 0

    log.info(f"Reconcile {len(rows)} positions ouvertes...")
    ok = 0
    failed = 0
    for r in rows:
        position_id, ticker, qty = r[0], r[1], r[2]
        log.info(f"  {ticker} (qty={qty}, pid={position_id})...")
        obs = reconcile_one(ticker)
        if obs["fetch_ok"]:
            if update_position_columns(position_id, obs):
                ok += 1
                log.info(
                    f"    -> {obs['price_native']:.4f} {obs['currency']} "
                    f"@ {obs['price_asof'][:19]} | "
                    f"FX {obs['fx_rate_to_eur']:.6f} @ {obs['fx_asof'][:19]}"
                )
            else:
                failed += 1
        else:
            failed += 1

    log.info(f"Done: {ok} ok, {failed} failed")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
