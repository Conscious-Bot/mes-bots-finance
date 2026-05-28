"""Signals + filings + insider handlers.

Extracted from bot/main.py Sprint 1.1 chunk 7 (2026-05-16, Day 5).
Mechanical move only, zero logic change.

Module exports (7 handlers):
- cmd_insider_buy_cluster        : /insider_buy_cluster [TICKER]
- cmd_recent_8k                  : /recent_8k
- cmd_eight_k_history            : /eight_k_history TICKER
- cmd_insider_digest             : /insider_digest (manual refresh)
- cmd_insider_cluster            : /insider_cluster TICKER

DEPS:
- Top-level: from intelligence.insider_digest import daily_insider_refresh, format_daily_insider_digest
from shared import edgar as edgar_mod
- Inline lazy: storage (as storage_mod), sqlite3, datetime
- storage._DB_PATH accessed directly for some queries

Note: scheduled_insider_refresh_job cron in bot/main.py also uses
daily_insider_refresh + format_daily_insider_digest (same imports there).
"""

from __future__ import annotations

from intelligence.insider_digest import daily_insider_refresh, format_daily_insider_digest
from shared import edgar as edgar_mod

__all__ = [
    "cmd_eight_k_history",
    "cmd_insider_buy_cluster",
    "cmd_insider_cluster",
    "cmd_insider_digest",
    "cmd_recent_8k",
]


async def cmd_insider_buy_cluster(update, ctx):  # noqa: ARG001
    """Phase C7 — List BUY clusters. Usage: /insider_buy_cluster [TICKER]"""

    parts = update.message.text.split()
    ticker = parts[1].upper() if len(parts) > 1 else None
    await _buy_cluster_impl(update, ticker)


async def cmd_recent_8k(update, ctx):  # noqa: ARG001
    """Sprint 1.2 Phase F dispatcher — /8k family.

    Usage:
      /8k [TICKER] [severity]    → recent 8-K filings (default, 60d window)
      /8k history TICKER         → full 8-K history for ticker (365d window)
      /recent_8k [...]           → alias for /8k (1 release cycle backward-compat)
      /eight_k_history TICKER    → alias for /8k history TICKER

    Severity values: CATASTROPHIC, HIGH, MEDIUM, LOW
    """
    parts = update.message.text.split()
    args = parts[1:] if len(parts) > 1 else []

    # Sub-action: /8k history TICKER → full history (365d)
    if args and args[0].lower() == "history":
        if len(args) < 2:
            await update.message.reply_text("Usage: /8k history <TICKER>")
            return
        await _eight_k_history_impl(update, args[1].upper())
        return

    # Default: list recent (60d), optional TICKER and severity filters
    ticker = None
    severity = None
    for p in args:
        p_up = p.upper()
        if p_up in ("CATASTROPHIC", "HIGH", "MEDIUM", "LOW"):
            severity = p.lower()
        else:
            ticker = p_up
    from intelligence import filings_8k
    from shared import storage as storage_mod

    rows = storage_mod.get_recent_8k_filings_db(ticker=ticker, severity=severity, days=60, limit=30)
    msg = filings_8k.format_8k_list(rows)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def _eight_k_history_impl(update, ticker: str) -> None:
    """Internal helper for /8k history TICKER — full 8-K history 365d window."""
    from intelligence import filings_8k
    from shared import storage as storage_mod

    rows = storage_mod.get_recent_8k_filings_db(ticker=ticker, days=365, limit=50)
    if not rows:
        await update.message.reply_text(f"No 8-K filings logged for {ticker} in last 365d.")
        return
    msg = filings_8k.format_8k_list(rows)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_eight_k_history(update, ctx):  # noqa: ARG001
    """Alias handler for /eight_k_history — delegates to /8k history dispatcher.

    Sprint 1.2 Phase F: kept 1 release cycle for backward-compat.
    """
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /eight_k_history <TICKER>  (or use /8k history <TICKER>)")
        return
    await _eight_k_history_impl(update, parts[1].upper())


async def cmd_insider_digest(update, context):  # noqa: ARG001
    """Manual: refresh insider snapshots and post digest."""
    await update.message.reply_text("⏳ Refreshing 13 tickers via SEC EDGAR (~30-60s)...")
    try:
        result = daily_insider_refresh()
        msg = format_daily_insider_digest(result)
    except Exception as e:
        msg = f"Error: {e}"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_insider_cluster(update, ctx):  # noqa: ARG001
    """Detect cluster buying/selling: /insider_cluster TICKER [days]"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /insider_cluster <TICKER> [days=14]")
        return
    ticker = parts[1].upper()
    days = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 14
    await _cluster_impl(update, ticker, days)


async def cmd_insiders(update, ctx):
    """Sprint 1.2 Phase E dispatcher - /insiders family.

    Usage:
      /insiders TICKER                  -> form 4 insider summary 90d (default)
      /insiders cluster TICKER [days]   -> detect cluster buying/selling
      /insiders buy_cluster [TICKER]    -> list BUY clusters logged
      /insiders digest                  -> manual refresh + post insider digest

    Backward-compat aliases preserved 1 release cycle:
      /insider_cluster, /insider_buy_cluster, /insider_digest
    """
    args = ctx.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  /insiders TICKER                 (form 4 summary 90d)\n"
            "  /insiders cluster TICKER [days]  (cluster detection)\n"
            "  /insiders buy_cluster [TICKER]   (BUY clusters logged)\n"
            "  /insiders digest                 (refresh + post digest)\n"
            "\n"
            "Ex: /insiders NVDA"
        )
        return

    action = args[0].lower()

    if action == "cluster":
        if len(args) < 2:
            await update.message.reply_text("Usage: /insiders cluster <TICKER> [days=14]")
            return
        ticker = args[1].upper()
        days = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 14
        await _cluster_impl(update, ticker, days)
        return

    if action == "buy_cluster":
        ticker = args[1].upper() if len(args) > 1 else None
        await _buy_cluster_impl(update, ticker)
        return

    if action == "digest":
        await cmd_insider_digest(update, ctx)
        return

    # Default: treat args[0] as ticker (preserves /insiders TICKER behavior)
    ticker = args[0].upper()
    await update.message.reply_text(f"Fetching Form 4 insiders {ticker} (15-30s, sleep entre fetches)...")
    try:
        activity = edgar_mod.get_insider_activity(ticker, days=90)
        msg = edgar_mod.format_insider_summary(activity)
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {type(e).__name__}: {e}")

async def _cluster_impl(update, ticker: str, days: int) -> None:
    """Internal: detect insider cluster buying/selling for ticker over N days.

    Used by cmd_insider_cluster (alias) and cmd_insiders (Sprint 1.2 Phase E
    dispatcher /insiders cluster). Body extracted verbatim, no dedent (body
    is at 4-space indent direct-in-function, target is same).
    """
    await update.message.reply_text("Scanning " + ticker + " insider cluster (" + str(days) + "d)...")
    try:
        cluster = edgar_mod.get_insider_cluster(ticker, days=days)
        await update.message.reply_text(edgar_mod.format_insider_cluster(cluster))
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))


async def _buy_cluster_impl(update, ticker) -> None:
    """Internal: list BUY clusters (filtered by ticker if provided).

    Used by cmd_insider_buy_cluster (alias) and cmd_insiders
    (/insiders buy_cluster). Body extracted verbatim, storage_mod import
    injected (L36: was BEFORE parse marker in original cmd_insider_buy_cluster).
    ticker can be None to list recent across all tickers.
    """
    from shared import storage as storage_mod

    if ticker:
        rows = storage_mod.get_buy_clusters_for_ticker(ticker, limit=20)
        if not rows:
            await update.message.reply_text(f"No BUY clusters logged for {ticker}.")
            return
        lines = [f"BUY CLUSTERS — {ticker} (last 20)"]
        for r in rows:
            ret30 = f"{r['return_30d']:+.2%}" if r["return_30d"] is not None else "pending"
            ret90 = f"{r['return_90d']:+.2%}" if r["return_90d"] is not None else "pending"
            lines.append(
                f"\n#{r['id']} {r['detected_at'][:10]} | {r['cluster_strength']:8s} | "
                f"{r['distinct_buyers']} buyers ${r['total_buy_m']:.1f}M @ ${r['price_at_detection'] or 0:.2f}"
            )
            lines.append(f"   J+30: {ret30}  |  J+90: {ret90}")
        msg = "\n".join(lines)
    else:
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=90)).strftime("%Y-%m-%d")
        import sqlite3

        conn = sqlite3.connect(storage_mod._DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM insider_buy_clusters_log WHERE date(detected_at) >= ? ORDER BY detected_at DESC LIMIT 20",
            (cutoff,),
        ).fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("No BUY clusters logged in last 90 days.")
            return
        lines = ["BUY CLUSTERS — last 90 days"]
        for r in rows:
            ret30 = f"{r['return_30d']:+.2%}" if r["return_30d"] is not None else "pending"
            lines.append(
                f"\n{r['ticker']:6s} {r['detected_at'][:10]} {r['cluster_strength']:8s} "
                f"n={r['distinct_buyers']} ${r['total_buy_m']:.1f}M J+30={ret30}"
            )
        msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)




async def cmd_signals_by_type(update, ctx):  # noqa: ARG001
    """Phase Digestion 3a — Usage: /signals_by_type catalyst|data|narrative|opinion [hours]"""
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage: /signals_by_type catalyst|data|narrative|opinion [hours=72]\n"
            "Returns signals sorted by adjusted materiality (score x corroboration boost)."
        )
        return
    sig_type = parts[1].lower()
    if sig_type not in ("catalyst", "data", "narrative", "opinion"):
        await update.message.reply_text(f"Invalid type: {sig_type}. Use catalyst|data|narrative|opinion.")
        return
    hours = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 72
    from shared import storage as storage_mod

    rows = storage_mod.get_signals_by_type(sig_type, since_hours=hours, limit=20)
    if not rows:
        await update.message.reply_text(f"No '{sig_type}' signals in last {hours}h.")
        return
    lines = [f"SIGNALS [{sig_type.upper()}] — last {hours}h ({len(rows)} found)"]
    for r in rows:
        boost = r.get("materiality_boost") or 1.0
        score = r.get("score") or 0
        adj = score * boost
        title = (r.get("title") or "?")[:100]
        src = r.get("source_name") or "?"
        lines.append(f"\n[adj={adj:.1f} raw={score} boost={boost:.1f}x] {src}")
        lines.append(f"  {title}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg)


async def cmd_insider_buy_cluster_stats(update, ctx):  # noqa: ARG001
    """Phase C7 — Empirical alpha summary across all logged BUY clusters."""
    from intelligence import insider_buy_cluster as ibc
    from shared import storage as storage_mod

    stats = storage_mod.get_buy_cluster_stats(since_days=365)
    if stats["n_total"] == 0:
        await update.message.reply_text(
            "No BUY clusters logged yet (last 365d).\nFirst clusters will appear after cron 6:20."
        )
        return
    msg = ibc.format_stats(stats)
    await update.message.reply_text(msg)
