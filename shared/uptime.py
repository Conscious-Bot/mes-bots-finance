"""Bot uptime monitoring — parses uptime.log heartbeat trace.

Heartbeat trace format (one entry per line, written by external cron):
    YYYY-MM-DD HH:MM:SS  (OK alive|FAIL bot down)

Non-matching lines (comments, blanks, malformed) are ignored silently.
KPI #1 reads this to compute rolling uptime percentage over configurable
window (default 30d).
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict


class UptimeStats(TypedDict):
    window_days: int
    total: int
    ok_count: int
    fail_count: int
    uptime_pct: float
    earliest_ts: str | None
    latest_ts: str | None
    expected_intervals: int


_LINE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})[\sT](\d{2}:\d{2}:\d{2})\s+(OK alive|FAIL bot down)\s*$")
_HEARTBEAT_INTERVAL_MIN = 5


def parse_uptime_log(path: Path, window_days: int = 30) -> UptimeStats:
    """Parse uptime.log and compute stats within rolling window."""
    expected_intervals = (24 * 60 // _HEARTBEAT_INTERVAL_MIN) * window_days
    base: UptimeStats = {
        "window_days": window_days,
        "total": 0,
        "ok_count": 0,
        "fail_count": 0,
        "uptime_pct": 0.0,
        "earliest_ts": None,
        "latest_ts": None,
        "expected_intervals": expected_intervals,
    }
    if not path.exists():
        return base
    cutoff = datetime.now() - timedelta(days=window_days)
    ok = fail = 0
    earliest: datetime | None = None
    latest: datetime | None = None
    for raw in path.read_text(errors="ignore").splitlines():
        m = _LINE_RE.match(raw)
        if not m:
            continue
        try:
            ts = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        if m.group(3) == "OK alive":
            ok += 1
        else:
            fail += 1
        if earliest is None or ts < earliest:
            earliest = ts
        if latest is None or ts > latest:
            latest = ts
    total = ok + fail
    return {
        "window_days": window_days,
        "total": total,
        "ok_count": ok,
        "fail_count": fail,
        "uptime_pct": ok / total if total > 0 else 0.0,
        "earliest_ts": earliest.isoformat() if earliest else None,
        "latest_ts": latest.isoformat() if latest else None,
        "expected_intervals": expected_intervals,
    }


def compute_kpi1(window_days: int = 30, path: Path | None = None) -> dict[str, str]:
    """Compute KPI #1 entry compatible with _kpi_compute_all dict format.

    Thresholds: GREEN >=95% / YELLOW 90-95% / RED <90% / INSUFFICIENT <100 samples.
    """
    if path is None:
        path = Path(__file__).resolve().parent.parent / "uptime.log"
    stats = parse_uptime_log(path, window_days=window_days)
    total = stats["total"]
    pct = stats["uptime_pct"]
    pct_str = f"{100 * pct:.1f}%"
    if total < 100:
        status = f"🔍 INSUFFICIENT DATA — N={total}, need >=100 samples"
    elif pct >= 0.95:
        status = "✅ GREEN"
    elif pct >= 0.90:
        status = f"⚠️ YELLOW — {pct_str} approaching 90% floor"
    else:
        status = f"🚨 RED — {pct_str} < 90% (action required)"
    return {
        "title": f"KPI #1: Bot uptime ({window_days}d)",
        "target": ">95%",
        "current": f"{pct_str} ({stats['ok_count']}/{total} OK, {stats['fail_count']} FAIL)",
        "status": status,
        "enforcement": "Alert si <95%, investiguer cron+caffeinate si <90%",
    }
