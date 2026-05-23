"""Snapshot quotidien de la valeur du portefeuille.

Ecrit une ligne/jour dans portfolio_snapshots (via shared.storage) : valeur
mark-to-market, base de cout, P&L, high-water-mark et drawdown reel. Pur logging
read-only cote decisions ; alimente la future courbe d'equity, le drawdown reel
(remplace le hack 8/20% statique sur Urgence) et le track record Path 6.

Idempotent sur la date (upsert). Aucun cout LLM.
"""

import math
from datetime import UTC, datetime

from shared import storage
from shared.prices import get_current_price_in_eur


def aggregate(positions: list[dict], prices: dict, prev_hwm: float = 0.0) -> dict | None:
    """Pur : agrege positions + prix EUR. None si aucun prix dispo. value/cost sur le meme set (price)."""
    total_value = 0.0
    total_cost = 0.0
    n_priced = 0
    detail: dict = {}
    for p in positions:
        tk = p["ticker"]
        qty = float(p.get("qty") or 0)
        avg = float(p.get("avg_cost") or 0)
        cost = qty * avg
        px = prices.get(tk)
        if px is None or not math.isfinite(px):
            detail[tk] = {"value": None, "cost": round(cost, 2), "pnl": None}
            continue
        value = qty * float(px)
        total_value += value
        total_cost += cost
        n_priced += 1
        pnl = (value / cost - 1) * 100 if cost else None
        detail[tk] = {"value": round(value, 2), "cost": round(cost, 2),
                      "pnl": round(pnl, 1) if pnl is not None else None}
    if n_priced == 0:
        return None
    hwm = max(prev_hwm or 0.0, total_value)
    drawdown = (total_value / hwm - 1) * 100 if hwm else 0.0
    return {
        "total_value_eur": round(total_value, 2),
        "total_cost_eur": round(total_cost, 2),
        "pnl_eur": round(total_value - total_cost, 2),
        "pnl_pct": round((total_value / total_cost - 1) * 100, 2) if total_cost else 0.0,
        "n_positions": len(positions),
        "n_priced": n_priced,
        "hwm_value_eur": round(hwm, 2),
        "drawdown_pct": round(drawdown, 2),
        "detail_json": detail,
    }


def compute_snapshot() -> dict | None:
    """Lit positions + prix live, retourne le snapshot du jour (ou None si rien de price)."""
    positions = storage.get_open_positions()
    if not positions:
        return None
    prices = {p["ticker"]: get_current_price_in_eur(p["ticker"]) for p in positions}
    snap = aggregate(positions, prices, storage.latest_snapshot_hwm() or 0.0)
    if snap is None:
        return None
    now = datetime.now(UTC)
    snap["snapshot_date"] = now.date().isoformat()
    snap["captured_at"] = now.isoformat()
    return snap


def daily_snapshot_job() -> None:
    """Cron quotidien : capture + upsert. Silencieux si rien a ecrire."""
    snap = compute_snapshot()
    if snap is None:
        return
    storage.upsert_portfolio_snapshot(snap)


if __name__ == "__main__":
    s = compute_snapshot()
    if s:
        storage.upsert_portfolio_snapshot(s)
        print(f"snapshot {s['snapshot_date']}: {s['total_value_eur']:.0f} EUR "
              f"(cost {s['total_cost_eur']:.0f}, P&L {s['pnl_pct']:+.1f}%, "
              f"DD {s['drawdown_pct']:.1f}%, {s['n_priced']}/{s['n_positions']} prix)")
    else:
        print("snapshot: rien a ecrire (0 position ou 0 prix)")
