"""Smart Calendar V1: earnings dates via yfinance.

refresh_earnings_calendar(tickers) persists upcoming events to DB.
Telegram /calendar reads from DB without yfinance latency.

Future v2: macro events hardcoded (FOMC/CPI/NFP), thesis cross-ref alerts.
"""

from datetime import UTC, date, datetime, timedelta

from shared import storage


def get_ticker_next_earnings(ticker):
    """Returns dict {date, description} for next earnings or None."""
    try:
        # SOCLE S1c (#111) : migré yf.Ticker.calendar → prices.get_calendar gateway (cache 6h).
        from shared.prices import get_calendar
        cal = get_calendar(ticker)
        if cal is None:
            return None
        ed = None
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if dates:
                ed = dates[0] if isinstance(dates, list) else dates
        else:
            try:
                if "Earnings Date" in cal.index:
                    ed = cal.loc["Earnings Date"].iloc[0]
            except Exception:
                pass
        if ed is None:
            return None
        if hasattr(ed, "strftime"):
            date_str = ed.strftime("%Y-%m-%d")
        else:
            date_str = str(ed)[:10]
        return {"date": date_str, "description": f"{ticker} earnings"}
    except Exception:
        return None


def refresh_earnings_calendar(tickers, days_ahead=90):
    """Refresh earnings dates for tickers within days_ahead. Returns count."""
    cutoff = (datetime.now(UTC) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    count = 0
    for tk in tickers:
        info = get_ticker_next_earnings(tk)
        if info is None or info["date"] < today or info["date"] > cutoff:
            continue
        storage.insert_event(
            event_type="earnings",
            ticker=tk,
            date=info["date"],
            description=info["description"],
        )
        count += 1
    return count


def format_calendar(events, days_ahead=14):
    if not events:
        return f"Aucun evenement dans les {days_ahead} prochains jours."
    lines = [f"Events {days_ahead}j ahead:"]
    today = datetime.now(UTC).date()
    for e in events:
        try:
            ev_date = datetime.fromisoformat(e["date"]).date()
            days_to = (ev_date - today).days
            day_str = f"+{days_to}j"
        except Exception:
            day_str = e["date"]
        line = f"  {e['date']} ({day_str:>4}) {e.get('event_type', '?'):8s} "
        if e.get("ticker"):
            line += f"{e['ticker']:<6} "
        if e.get("description"):
            line += f"- {e['description']}"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        test_tickers = ["NVDA", "AMD", "TSM", "AVGO", "MU", "MSFT", "GOOGL", "META", "AAPL", "CRWD"]
        print(f"Refresh earnings for {len(test_tickers)} test tickers...")
        n = refresh_earnings_calendar(test_tickers)
        print(f"OK {n} events upserted")
        events = storage.get_upcoming_events(days_ahead=90)
        print(format_calendar(events, days_ahead=90))
    else:
        events = storage.get_upcoming_events(days_ahead=14)
        print(format_calendar(events))


def get_pre_event_thesis_alerts(days_ahead=7):
    """For each upcoming event with an active thesis on the same ticker, return alert info."""
    events = storage.get_upcoming_events(days_ahead=days_ahead)
    if not events:
        return []
    theses = []
    try:
        theses = storage.list_theses(status="active")
    except (TypeError, AttributeError):
        try:
            all_theses = storage.list_theses() if hasattr(storage, "list_theses") else []
            theses = [t for t in all_theses if t.get("status") == "active"]
        except Exception:
            theses = []
    theses_by_ticker = {t.get("ticker"): t for t in theses if t.get("ticker")}
    if not theses_by_ticker:
        return []
    alerts = []
    for e in events:
        tk = e.get("ticker")
        if not tk or tk not in theses_by_ticker:
            continue
        th = theses_by_ticker[tk]
        try:
            ev_date = datetime.fromisoformat(e["date"]).date()
            days_to = (ev_date - datetime.now(UTC).date()).days
        except Exception:
            days_to = None
        last_touch = th.get("last_revisit_at") or th.get("created_at") or ""
        days_since = None
        if last_touch:
            try:
                last_dt = datetime.fromisoformat(str(last_touch).split(".")[0].replace("Z", "")).replace(tzinfo=UTC)
                days_since = (datetime.now(UTC) - last_dt).days
            except Exception:
                pass
        alerts.append(
            {
                "ticker": tk,
                "event_date": e["date"],
                "event_type": e["event_type"],
                "days_to_event": days_to,
                "thesis_id": th.get("id"),
                "thesis_last_touch_days": days_since,
            }
        )
    return alerts


def format_alerts(alerts):
    if not alerts:
        return None
    lines = ["PRE-EVENT ALERTS:"]
    for a in alerts:
        days = a["days_to_event"]
        days_str = f"+{days}j" if days is not None else a["event_date"]
        line = f"  {a['ticker']} {a['event_type']} {days_str} (thesis #{a['thesis_id']}"
        if a["thesis_last_touch_days"] is not None:
            line += f", last touch {a['thesis_last_touch_days']}j"
        line += ") -> /thesis_revisit"
        lines.append(line)
    return "\n".join(lines)


# ============================================================================
# MACRO EVENTS (FOMC + NFP + CPI)
# FOMC dates verified against fed.gov May 2026.
# NFP = first Friday of month (deterministic).
# CPI = BLS approximate (verify against bls.gov/schedule/news_release/cpi.htm).
# ============================================================================
import calendar as _cal_mod

# Day-2 (decision/press-conf day) for each remaining 2026 FOMC
FOMC_DATES_2026 = [
    ("2026-06-17", False, "FOMC rate decision + press conf"),
    ("2026-07-29", False, "FOMC rate decision + press conf"),
    ("2026-09-16", True, "FOMC rate decision + SEP + dot plot"),
    ("2026-10-28", False, "FOMC rate decision + press conf"),
    ("2026-12-09", True, "FOMC rate decision + SEP + dot plot"),
]

# CPI release dates 2026 (approximate, BLS ~10-15th of month for prior month)
CPI_DATES_2026 = [
    ("2026-05-13", "CPI release (April data)"),
    ("2026-06-11", "CPI release (May data)"),
    ("2026-07-15", "CPI release (June data)"),
    ("2026-08-12", "CPI release (July data)"),
    ("2026-09-11", "CPI release (August data)"),
    ("2026-10-15", "CPI release (September data)"),
    ("2026-11-13", "CPI release (October data)"),
    ("2026-12-10", "CPI release (November data)"),
]


def _first_friday(year: int, month: int) -> date:
    for d in _cal_mod.Calendar().itermonthdates(year, month):
        if d.month == month and d.weekday() == 4:
            return d
    raise ValueError("no Friday found")


def get_nfp_dates(start_year: int = 2026, end_year: int = 2027) -> list:
    today = date.today()
    out = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            d = _first_friday(y, m)
            if d >= today:
                out.append((d.isoformat(), "NFP / nonfarm payrolls release"))
    return out


def seed_macro_events() -> int:
    """Insert FOMC + NFP + CPI into events table. Idempotent (INSERT OR IGNORE)."""
    from shared.storage import db

    today_str = date.today().isoformat()
    with db() as cx:
        for d_str, is_sep, desc in FOMC_DATES_2026:
            if d_str < today_str:
                continue
            full = desc + (" (SEP / dot plot)" if is_sep else "")
            cx.execute(
                "INSERT OR IGNORE INTO events (event_type, ticker, date, description) VALUES (?, ?, ?, ?)",
                ("fomc", "MACRO", d_str, full),
            )
        for d_str, desc in get_nfp_dates():
            cx.execute(
                "INSERT OR IGNORE INTO events (event_type, ticker, date, description) VALUES (?, ?, ?, ?)",
                ("nfp", "MACRO", d_str, desc),
            )
        for d_str, desc in CPI_DATES_2026:
            if d_str < today_str:
                continue
            cx.execute(
                "INSERT OR IGNORE INTO events (event_type, ticker, date, description) VALUES (?, ?, ?, ?)",
                ("cpi", "MACRO", d_str, desc),
            )
        cx.commit()
        row = cx.execute(
            "SELECT COUNT(*) AS n FROM events WHERE event_type IN ('fomc','nfp','cpi') AND date >= ?", (today_str,)
        ).fetchone()
        return row["n"] if row else 0


def format_macro_calendar(days_ahead: int = 90) -> str:
    """Formatted macro events for next N days."""
    from shared.storage import db

    today = date.today()
    end = (today + timedelta(days=days_ahead)).isoformat()
    with db() as cx:
        rows = cx.execute(
            "SELECT date, event_type, description FROM events "
            "WHERE event_type IN ('fomc','nfp','cpi') AND date >= ? AND date <= ? "
            "ORDER BY date",
            (today.isoformat(), end),
        ).fetchall()
    if not rows:
        return "(no macro events in next 90d — run seed_macro_events)"
    icons = {"fomc": "🏦", "nfp": "💼", "cpi": "📊"}
    lines = [f"=== MACRO CALENDAR (next {days_ahead}d) ==="]
    for r in rows:
        d_obj = datetime.strptime(r["date"], "%Y-%m-%d").date()
        days_out = (d_obj - today).days
        icon = icons.get(r["event_type"], "•")
        lines.append(f"  {icon} {r['date']} (+{days_out}d) — {r['description']}")
    return "\n".join(lines)
