"""
Position tracking — actual portfolio holdings (qty + avg_cost per ticker).
Full buy/sell history in position_events. Integrates with Phase 5 + 6 alerts.
"""

import logging
from datetime import datetime

from shared import prices
from shared.storage import db

log = logging.getLogger(__name__)


def _ensure_tables(cx) -> None:
    cx.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            qty REAL NOT NULL,
            avg_cost REAL NOT NULL,
            realized_pnl REAL DEFAULT 0,
            opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            status TEXT DEFAULT 'open'
        )
    """)
    cx.execute("""
        CREATE TABLE IF NOT EXISTS position_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            ticker TEXT NOT NULL,
            event_type TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL,
            pnl REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)
    cx.execute("CREATE INDEX IF NOT EXISTS idx_positions_ticker_status ON positions(ticker, status)")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_position_events_ticker ON position_events(ticker, timestamp)")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def cost_in(avg_cost_eur: float | None, target_cur: str = "USD") -> float | None:
    """Convert EUR-stored avg_cost to target currency. Canonical per ADR 005 (Day 13).

    Single source of truth: positions.avg_cost is ALWAYS stored EUR (Day 7
    broker import convention). Replaces 4+ ad-hoc handlers that wrongly
    multiplied by fx_native_to_X (treating EUR-stored value as native),
    producing 1000x+ P&L errors on JPY/KRW tickers (Lesson 15 audit Day 13).
    """
    if avg_cost_eur is None:
        return None
    tc = target_cur.upper()
    if tc == "EUR":
        return avg_cost_eur
    from shared.prices import get_fx_rate
    fx = get_fx_rate("EUR", tc) or 1.0
    return avg_cost_eur * fx



def set_position(ticker: str, qty: float, avg_cost: float, notes: str | None = None) -> dict:
    """Set/replace position. Use for bootstrap of existing holdings."""
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        existing = cx.execute("SELECT id FROM positions WHERE ticker=? AND status='open'", (ticker,)).fetchone()
        if existing:
            cx.execute(
                "UPDATE positions SET qty=?, avg_cost=?, last_updated=?, notes=? WHERE id=?",
                (qty, avg_cost, _now(), notes, existing["id"]),
            )
            pid = existing["id"]
            cx.execute(
                "INSERT INTO position_events (position_id, ticker, event_type, qty, price, notes) VALUES (?, ?, 'adjust', ?, ?, ?)",
                (pid, ticker, qty, avg_cost, notes or "set_position override"),
            )
        else:
            cur = cx.execute(
                "INSERT INTO positions (ticker, qty, avg_cost, notes) VALUES (?, ?, ?, ?)",
                (ticker, qty, avg_cost, notes),
            )
            pid = cur.lastrowid
            cx.execute(
                "INSERT INTO position_events (position_id, ticker, event_type, qty, price, notes) VALUES (?, ?, 'buy', ?, ?, ?)",
                (pid, ticker, qty, avg_cost, notes or "initial position"),
            )
        cx.commit()
    result = get_position(ticker)
    assert result is not None, "position lookup after upsert failed"
    return result


def add_buy(ticker: str, qty: float, price: float, notes: str | None = None) -> dict:
    """Add buy; weighted-avg cost recalc on existing position, or create new."""
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        existing = cx.execute(
            "SELECT id, qty, avg_cost FROM positions WHERE ticker=? AND status='open'", (ticker,)
        ).fetchone()
        if existing:
            old_qty, old_avg = existing["qty"], existing["avg_cost"]
            new_qty = old_qty + qty
            new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else 0
            cx.execute(
                "UPDATE positions SET qty=?, avg_cost=?, last_updated=? WHERE id=?",
                (new_qty, new_avg, _now(), existing["id"]),
            )
            pid = existing["id"]
        else:
            cur = cx.execute(
                "INSERT INTO positions (ticker, qty, avg_cost, notes) VALUES (?, ?, ?, ?)", (ticker, qty, price, notes)
            )
            pid = cur.lastrowid
        cx.execute(
            "INSERT INTO position_events (position_id, ticker, event_type, qty, price, notes) VALUES (?, ?, 'buy', ?, ?, ?)",
            (pid, ticker, qty, price, notes),
        )
        cx.commit()
    result = get_position(ticker)
    assert result is not None, "position lookup after upsert failed"
    return result


def add_sell(ticker: str, qty: float, price: float, notes: str | None = None) -> dict:
    """Sell shares. Computes realized P&L. Auto-closes if qty → 0."""
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        existing = cx.execute(
            "SELECT id, qty, avg_cost, realized_pnl FROM positions WHERE ticker=? AND status='open'", (ticker,)
        ).fetchone()
        if not existing:
            raise ValueError(f"No open position for {ticker}")
        if qty > existing["qty"] + 1e-9:
            raise ValueError(f"Sell qty {qty} > position qty {existing['qty']}")
        new_qty = existing["qty"] - qty
        pnl = qty * (price - existing["avg_cost"])
        new_realized = (existing["realized_pnl"] or 0) + pnl
        if new_qty <= 1e-6:
            cx.execute(
                "UPDATE positions SET qty=0, realized_pnl=?, status='closed', last_updated=? WHERE id=?",
                (new_realized, _now(), existing["id"]),
            )
            closed = True
        else:
            cx.execute(
                "UPDATE positions SET qty=?, realized_pnl=?, last_updated=? WHERE id=?",
                (new_qty, new_realized, _now(), existing["id"]),
            )
            closed = False
        cx.execute(
            "INSERT INTO position_events (position_id, ticker, event_type, qty, price, pnl, notes) VALUES (?, ?, 'sell', ?, ?, ?, ?)",
            (existing["id"], ticker, qty, price, pnl, notes),
        )
        cx.commit()
    return {
        "ticker": ticker,
        "sold_qty": qty,
        "sold_price": price,
        "avg_cost": existing["avg_cost"],
        "realized_pnl_event": pnl,
        "realized_pnl_total": new_realized,
        "remaining_qty": max(new_qty, 0),
        "closed": closed,
    }


def _enrich_with_live(d: dict, target_cur: str = "EUR") -> dict:
    """Enrich position dict with live current_price, market_value, unrealized_pnl.

    Day 13 ADR 005: FM-10 latent currency mix RESOLVED. avg_cost is EUR-canonical
    stored (empirical truth confirmed Day 13 audit, contrary to Day 11 Batch 4A
    aspirational comment about NATIVE storage). Convert avg_cost EUR -> target_cur
    via cost_in helper for coherent (price, cost) pair in same currency.
    """
    if d["qty"] <= 0:
        return d
    try:
        p = prices.get_current_price_in(d["ticker"], target_cur)
        if p:
            avg_cost_target = cost_in(d["avg_cost"], target_cur)
            d["current_price"] = p
            d["market_value"] = p * d["qty"]
            if avg_cost_target:
                d["unrealized_pnl"] = (p - avg_cost_target) * d["qty"]
                d["unrealized_pct"] = ((p - avg_cost_target) / avg_cost_target)
    except Exception as e:
        log.warning(f"live price fetch {d['ticker']}: {e}")
    return d


def get_position(ticker: str) -> dict | None:
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        r = cx.execute("SELECT * FROM positions WHERE ticker=? AND status='open'", (ticker,)).fetchone()
    if not r:
        return None
    return _enrich_with_live(dict(r))


def list_positions(status: str = "open") -> list:
    with db() as cx:
        _ensure_tables(cx)
        rows = cx.execute("SELECT * FROM positions WHERE status=? ORDER BY ticker", (status,)).fetchall()
    out = [_enrich_with_live(dict(r)) for r in rows]
    out.sort(key=lambda x: -(x.get("market_value") or 0))
    return out


def get_history(ticker: str, limit: int = 50) -> list:
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        rows = cx.execute(
            "SELECT * FROM position_events WHERE ticker=? ORDER BY id DESC LIMIT ?", (ticker, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def format_positions_summary(positions: list) -> str:
    if not positions:
        return "No open positions."
    lines = ["📊 Open positions:"]
    total_mv, total_upl = 0, 0
    for p in positions:
        qty, avg = p.get("qty", 0), p.get("avg_cost", 0)
        mv, upl, upct = p.get("market_value"), p.get("unrealized_pnl"), p.get("unrealized_pct")
        cur = p.get("current_price")
        if mv:
            total_mv += mv
        if upl:
            total_upl += upl
        if cur:
            sign = "🟢" if (upl or 0) > 0 else "🔴"
            # ADR 005: avg_cost EUR canonical; _enrich_with_live default target_cur=EUR
            # so avg/cur/mv/upl all in EUR. Label € (no conversion needed).
            lines.append(f"  {sign} {p['ticker']:6s} {qty:>9.3f} @ €{avg:.2f} → €{cur:.2f}")
            lines.append(f"       MV €{mv:>10,.0f}  UPL €{upl:+,.0f} ({upct:+.1%})")
        else:
            lines.append(f"  ⚪ {p['ticker']:6s} {qty:>9.3f} @ €{avg:.2f} (no live price)")
    lines.append("")
    lines.append(f"  Total MV:  €{total_mv:>11,.0f}")
    lines.append(f"  Total UPL: €{total_upl:>+11,.0f}")
    return "\n".join(lines)


def format_position_detail(p: dict, history: list) -> str:
    if not p:
        return "No open position."
    lines = [f"📋 {p['ticker']} position"]
    lines.append(f"  Qty:            {p['qty']:.3f}")
    lines.append(f"  Avg cost:       €{p['avg_cost']:.2f}")  # ADR 005: EUR canonical
    lines.append(f"  Realized PnL:   ${(p.get('realized_pnl') or 0):+,.2f}")
    if p.get("current_price"):
        lines.append(f"  Current price:  €{p['current_price']:.2f}")  # ADR 005: EUR via _enrich_with_live
        lines.append(f"  Market value:   €{p['market_value']:,.2f}")
        lines.append(f"  Unrealized PnL: €{p['unrealized_pnl']:+,.2f} ({p['unrealized_pct']:+.1%})")
    lines.append(f"  Opened:         {p.get('opened_at', '?')[:10]}")
    if history:
        lines.append("")
        lines.append("  History (last 10):")
        for h in history[:10]:
            sign = "+" if h["event_type"] == "buy" else "-" if h["event_type"] == "sell" else "~"
            ln = f"    {h.get('timestamp', '')[:10]}  {h['event_type']:6s} {sign}{h['qty']:.3f} @ ${h.get('price', 0):.2f}"
            if h.get("pnl") is not None:
                ln += f"  PnL ${h['pnl']:+,.2f}"
            lines.append(ln)
    return "\n".join(lines)
