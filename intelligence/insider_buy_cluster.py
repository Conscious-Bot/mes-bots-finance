"""Phase C7 — Insider BUY cluster empirical tracking.

Builds on existing edgar.get_insider_cluster (Phase 12.1) but adds:
- CMP-grade 30d default window
- Persistent log of every detected cluster
- Auto-resolve return at J+30 and J+90 vs price_at_detection
- Dedup logic (7d cooldown per ticker)
- Empirical alpha aggregation
"""

import logging
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)


def _close_at_or_after(ticker, target_date):
    """Return close price on or just after target_date (handles weekends/holidays)."""
    try:
        import yfinance as yf

        start = (target_date - timedelta(days=2)).strftime("%Y-%m-%d")
        end = (target_date + timedelta(days=10)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end)
        if hist.empty:
            return None
        for idx, row in hist.iterrows():
            if idx.date() >= target_date.date():
                return float(row["Close"])
        return None
    except Exception as e:
        log.warning(f"price fetch failed {ticker} @ {target_date}: {e}")
        return None


def detect_and_log_buy_clusters(watchlist, window_days=30, dedup_days=7):
    """Run detection on watchlist tickers. Returns list of NEW clusters (not deduped)."""
    from shared import edgar, storage

    new_found = []
    detected_at = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(UTC).replace(tzinfo=None)
    for tk in watchlist:
        try:
            brief = edgar.get_insider_brief(tk, ttl_hours=24)
            if not brief or (brief.get("n_buys") or 0) == 0:
                continue
            cluster = edgar.get_insider_cluster(tk, days=window_days)
            if not cluster.get("is_buy_cluster"):
                continue
            recent = storage.get_recent_buy_cluster_log(tk, days=dedup_days)
            if recent:
                log.info(f"BUY cluster {tk} suppressed (recent log id={recent['id']})")
                continue
            price = _close_at_or_after(tk, today)
            cid = storage.log_buy_cluster(tk, detected_at, window_days, cluster, price)
            cluster["_log_id"] = cid
            cluster["_price_at_detection"] = price
            new_found.append(cluster)
            log.info(f"BUY cluster logged: {tk} id={cid} strength={cluster.get('cluster_strength')} price=${price}")
        except Exception as e:
            log.warning(f"detect_and_log {tk} failed: {e}")
    return new_found


def resolve_pending_returns(checkpoint_days):
    """Resolve return_30d or return_90d for clusters past their checkpoint."""
    from shared import storage

    pending = storage.get_unresolved_buy_clusters(checkpoint_days)
    resolved_now = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    resolved_list = []
    for c in pending:
        try:
            detected = datetime.strptime(c["detected_at"][:10], "%Y-%m-%d")
            target_date = detected + timedelta(days=checkpoint_days)
            if target_date > datetime.now(UTC).replace(tzinfo=None):
                continue
            price_now = _close_at_or_after(c["ticker"], target_date)
            if not price_now or not c["price_at_detection"]:
                continue
            return_pct = (price_now - c["price_at_detection"]) / c["price_at_detection"]
            storage.resolve_buy_cluster_return(c["id"], checkpoint_days, return_pct, resolved_now)
            resolved_list.append(
                {
                    "id": c["id"],
                    "ticker": c["ticker"],
                    "checkpoint": checkpoint_days,
                    "return": return_pct,
                    "price_then": c["price_at_detection"],
                    "price_now": price_now,
                }
            )
            log.info(f"BUY cluster resolved id={c['id']} {c['ticker']} J+{checkpoint_days} return={return_pct:.2%}")
        except Exception as e:
            log.warning(f"resolve cluster id={c['id']} failed: {e}")
    return resolved_list


def format_stats(stats):
    lines = ["INSIDER BUY CLUSTER — EMPIRICAL ALPHA (your data)"]
    lines.append("")
    lines.append(f"Clusters logged: {stats['n_total']}")
    lines.append(f"  Resolved J+30: {stats['n_resolved_30d']}")
    lines.append(f"  Resolved J+90: {stats['n_resolved_90d']}")
    if stats["stats_30d"]:
        s = stats["stats_30d"]
        lines.append("")
        lines.append(f"J+30 returns (n={s['n']}):")
        lines.append(f"  Mean:   {s['mean']:+.2%}")
        lines.append(f"  Median: {s['median']:+.2%}")
        lines.append(f"  Hit rate: {s['hit_rate']:.0%}")
        lines.append(f"  Best:  {s['best']:+.2%}")
        lines.append(f"  Worst: {s['worst']:+.2%}")
    if stats["stats_90d"]:
        s = stats["stats_90d"]
        lines.append("")
        lines.append(f"J+90 returns (n={s['n']}):")
        lines.append(f"  Mean:   {s['mean']:+.2%}")
        lines.append(f"  Median: {s['median']:+.2%}")
        lines.append(f"  Hit rate: {s['hit_rate']:.0%}")
        lines.append(f"  Best:  {s['best']:+.2%}")
        lines.append(f"  Worst: {s['worst']:+.2%}")
    if stats["by_strength"]:
        lines.append("")
        lines.append("By cluster strength (J+30):")
        for s, v in stats["by_strength"].items():
            lines.append(f"  {s:10s} n={v['n']:3d}  mean={v['mean_30d']:+.2%}")
    lines.append("")
    lines.append("Reference: Cohen-Malloy-Pomorski 2012 documented +82bp/month alpha.")
    return "\n".join(lines)
