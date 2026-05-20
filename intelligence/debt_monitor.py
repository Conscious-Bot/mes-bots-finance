"""Debt Crisis Monitor — phase-based tail-risk overlay (ADR 006, Day 14).

15 indicators across 3 tiers, deterministic threshold classification.
Composite scoring → overall debt crisis phase (1/2/3/4).

Tier 1 (daily, weight 1.0):  TYX, Gold, USDJPY, VIX, HY_OAS, DXY, BTC
Tier 2 (weekly, weight 0.75): MOVE, KRE, T10Y2Y, BankReserves, CopperGold
Tier 3 (monthly, weight 0.5): CoreCPI, FedBalance, ISMMfg

Reads:
* yfinance for market price tickers (real-time)
* shared.macro._fred_series for FRED series (FRED_API_KEY required)

Writes:
* debt_signals (per-indicator history)
* debt_composite (computed phase timeline)

Phase 1 = normal, Phase 2 = stress, Phase 3 = severe, Phase 4 = crisis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from shared import macro
from shared.storage import db

log = logging.getLogger(__name__)

# ============================================================
# INDICATOR CONFIG — 15 indicators, phase boundaries per Olivier spec
# ============================================================

# Phase ranges: list of (low_inclusive, high_exclusive, phase_id) tuples.
# Value below lowest range → phase 1 (assume safe). Value above highest → phase 4.

INDICATOR_CONFIG: dict[str, dict[str, Any]] = {
    # ---- Tier 1: critical, daily ----
    "TYX": {
        "tier": 1, "weight": 1.0, "source": "yfinance:^TYX",
        "label": "30Y Treasury Yield (%)",
        "phase_ranges": [
            (0, 5.5, 1), (5.5, 5.85, 2), (5.85, 6.5, 3), (6.5, 999, 4),
        ],
    },
    "Gold": {
        "tier": 1, "weight": 1.0, "source": "yfinance:GC=F",
        "label": "Gold Spot ($/oz)",
        "phase_ranges": [
            (0, 3500, 1), (3500, 4000, 2), (4000, 5000, 3), (5000, 99999, 4),
        ],
    },
    "USDJPY": {
        "tier": 1, "weight": 1.0, "source": "yfinance:USDJPY=X",
        "label": "USD/JPY",
        "phase_ranges": [
            (0, 170, 1), (170, 180, 2), (180, 195, 3), (195, 999, 4),
        ],
    },
    "VIX": {
        "tier": 1, "weight": 1.0, "source": "yfinance:^VIX",
        "label": "VIX",
        "phase_ranges": [
            (0, 25, 1), (25, 35, 2), (35, 50, 3), (50, 999, 4),
        ],
    },
    "HY_OAS": {
        "tier": 1, "weight": 1.0, "source": "macro:hy_oas",
        "label": "HY OAS (bp)",
        "phase_ranges": [
            (0, 450, 1), (450, 600, 2), (600, 900, 3), (900, 9999, 4),
        ],
    },
    "DXY": {
        "tier": 1, "weight": 1.0, "source": "yfinance:DX-Y.NYB",
        "label": "DXY Dollar Index",
        # Asymmetric: stress either side of [95-108]; <90 = reserve status concern
        "phase_ranges": [
            (0, 90, 4), (90, 95, 3), (95, 108, 1), (108, 115, 2), (115, 999, 3),
        ],
    },
    "BTC": {
        "tier": 1, "weight": 1.0, "source": "yfinance:BTC-USD",
        "label": "Bitcoin ($)",
        # Signal: extreme up = monetary debasement narrative; extreme down = risk-off
        "phase_ranges": [
            (0, 30000, 3), (30000, 100000, 1), (100000, 150000, 2), (150000, 999999, 3),
        ],
    },

    # ---- Tier 2: important, weekly ----
    "MOVE": {
        "tier": 2, "weight": 0.75, "source": "yfinance:^MOVE",
        "label": "MOVE Bond Vol",
        "phase_ranges": [
            (0, 100, 1), (100, 130, 2), (130, 180, 3), (180, 999, 4),
        ],
    },
    "KRE": {
        "tier": 2, "weight": 0.75, "source": "yfinance:KRE",
        "label": "Regional Banks ETF ($)",
        # Inverse: lower = more stress
        "phase_ranges": [
            (0, 30, 4), (30, 40, 3), (40, 45, 2), (45, 999, 1),
        ],
    },
    "T10Y2Y": {
        "tier": 2, "weight": 0.75, "source": "macro:yield_curve",
        "label": "10Y-2Y spread (%)",
        # Bull steepening signal: very positive after long inversion = fiscal dominance
        "phase_ranges": [
            (-999, 0, 1), (0, 1.0, 1), (1.0, 2.0, 2), (2.0, 999, 3),
        ],
    },
    "BankReserves": {
        "tier": 2, "weight": 0.75, "source": "fred:WRESBAL",
        "label": "Bank Reserves at Fed ($B)",
        # Reserves of Depository Institutions, weekly, billions USD.
        # Direct stress proxy: Sept 2019 repo blowup at ~$1.4T forced Fed QE restart.
        # LCLOR (Lowest Comfortable Operating Level) estimated $2.5-3T currently.
        # < $2T = Phase 4 crisis territory (forced Fed intervention).
        # Replaces RepoSRF (ON RRP) which was ambiguous post-QT — see ADR 006 audit.
        "phase_ranges": [
            (0, 2000, 4), (2000, 2500, 3), (2500, 3000, 2), (3000, 99999, 1),
        ],
    },
    "CopperGold": {
        "tier": 2, "weight": 0.75, "source": "derived:copper_gold",
        "label": "Copper/Gold ratio",
        # Lower = recession pricing
        "phase_ranges": [
            (0, 0.0006, 4), (0.0006, 0.0008, 3), (0.0008, 0.0012, 2), (0.0012, 999, 1),
        ],
    },

    # ---- Tier 3: background, monthly ----
    "CoreCPI": {
        "tier": 3, "weight": 0.5, "source": "fred:CPILFESL_yoy",
        "label": "Core CPI YoY (%)",
        "phase_ranges": [
            (-999, 3.5, 1), (3.5, 4.5, 2), (4.5, 6.0, 3), (6.0, 999, 4),
        ],
    },
    "FedBalance": {
        "tier": 3, "weight": 0.5, "source": "fred:WALCL",
        "label": "Fed Balance Sheet ($M)",
        # Static reference; trend matters more than level. Placeholder phases.
        "phase_ranges": [
            (0, 7000000, 1), (7000000, 8000000, 2), (8000000, 9000000, 3), (9000000, 99999999, 4),
        ],
    },
    "MfgIP_yoy": {
        "tier": 3, "weight": 0.5, "source": "fred:IPMAN_yoy",
        "label": "Mfg Industrial Production YoY (%)",
        # ISM Mfg PMI replacement: FRED dropped ISM series 2024+.
        # YoY % change of IPMAN as proxy. >2% = expansion (P1),
        # 0-2% = sluggish (P2), -2 to 0 = contraction (P3), <-2 = recession (P4).
        "phase_ranges": [
            (-999, -2, 4), (-2, 0, 3), (0, 2, 2), (2, 999, 1),
        ],
    },
}

# ============================================================
# Schema
# ============================================================


def _ensure_tables() -> None:
    with db() as cx:
        cx.execute("""
            CREATE TABLE IF NOT EXISTS debt_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                value REAL,
                phase INTEGER,
                raw_source TEXT,
                UNIQUE(indicator_name, timestamp)
            )
        """)
        cx.execute(
            "CREATE INDEX IF NOT EXISTS idx_debt_signals_ind_ts "
            "ON debt_signals(indicator_name, timestamp DESC)"
        )
        cx.execute("""
            CREATE TABLE IF NOT EXISTS debt_composite (
                timestamp TEXT PRIMARY KEY,
                score REAL NOT NULL,
                phase INTEGER NOT NULL,
                tier_breakdown TEXT
            )
        """)


# ============================================================
# Fetchers
# ============================================================


def _fetch_yfinance(ticker: str) -> float | None:
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="5d", interval="1d")
        if h.empty:
            return None
        return float(h["Close"].iloc[-1])
    except Exception as e:
        log.warning(f"yfinance {ticker}: {e}")
        return None


def _fetch_fred_latest(series_id: str) -> float | None:
    obs = macro._fred_series(series_id, limit=1)
    if obs:
        return float(obs[0]["value"])
    return None


def _fetch_fred_cpi_yoy() -> float | None:
    """Core CPI YoY %. obs[11] = 12 months back, obs[0] = latest."""
    obs = macro._fred_series("CPILFESL", limit=14)
    if not obs or len(obs) < 12:
        return None
    current = obs[0]["value"]
    year_ago = obs[11]["value"]  # 12 calendar months back
    return (current - year_ago) / year_ago * 100


def _fetch_fred_ipman_yoy() -> float | None:
    """Manufacturing Industrial Production YoY %. ISM PMI replacement (paywalled)."""
    obs = macro._fred_series("IPMAN", limit=14)
    if not obs or len(obs) < 12:
        return None
    current = obs[0]["value"]
    year_ago = obs[11]["value"]
    return (current - year_ago) / year_ago * 100


def fetch_indicator(name: str) -> float | None:
    """Dispatch fetch by INDICATOR_CONFIG[name]['source']."""
    cfg = INDICATOR_CONFIG.get(name)
    if not cfg:
        log.warning(f"unknown indicator: {name}")
        return None
    src = cfg["source"]

    if src.startswith("yfinance:"):
        return _fetch_yfinance(src.split(":", 1)[1])

    if src == "macro:hy_oas":
        r = macro.get_hy_oas()
        return r.get("bp") if r and "error" not in r else None

    if src == "macro:yield_curve":
        r = macro.get_yield_curve_spread()
        return r.get("spread_pct") if r else None

    if src.startswith("fred:"):
        sid = src.split(":", 1)[1]
        if sid == "CPILFESL_yoy":
            return _fetch_fred_cpi_yoy()
        if sid == "IPMAN_yoy":
            return _fetch_fred_ipman_yoy()
        return _fetch_fred_latest(sid)

    if src == "derived:copper_gold":
        copper = _fetch_yfinance("HG=F")
        gold = _fetch_yfinance("GC=F")
        if copper is None or gold is None or gold == 0:
            return None
        return copper / gold

    log.warning(f"unknown source scheme: {src}")
    return None


# ============================================================
# Phase classification + scoring
# ============================================================


def classify_phase(value: float, phase_ranges: list[tuple[float, float, int]]) -> int:
    """Find matching phase for value; default Phase 4 if above all ranges."""
    for low, high, phase in phase_ranges:
        if low <= value < high:
            return phase
    return 4


# Phase weight: 1=1pt, 2=8pts, 3=16pts, 4=32pts (per Olivier spec)
_PHASE_WEIGHT = {1: 1, 2: 8, 3: 16, 4: 32}


def _score_contribution(indicator_weight: float, phase: int) -> float:
    return indicator_weight * _PHASE_WEIGHT[phase]


def composite_phase_from_score(score: float) -> int:
    # Scaled for 15 indicators (max ~390 theoretical)
    if score < 22:
        return 1
    if score < 60:
        return 2
    if score < 115:
        return 3
    return 4


# ============================================================
# Persistence
# ============================================================


def persist_signal(name: str, value: float | None, phase: int | None) -> None:
    _ensure_tables()
    ts = datetime.now(UTC).isoformat()
    cfg = INDICATOR_CONFIG.get(name, {})
    raw_source = cfg.get("source", "?")
    with db() as cx:
        cx.execute(
            "INSERT OR REPLACE INTO debt_signals (indicator_name, timestamp, value, phase, raw_source) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, ts, value, phase, raw_source),
        )


def persist_composite(score: float, phase: int, breakdown: dict) -> None:
    import json
    _ensure_tables()
    ts = datetime.now(UTC).isoformat()
    with db() as cx:
        cx.execute(
            "INSERT OR REPLACE INTO debt_composite (timestamp, score, phase, tier_breakdown) "
            "VALUES (?, ?, ?, ?)",
            (ts, score, phase, json.dumps(breakdown, sort_keys=True)),
        )


def get_latest_indicator(name: str) -> dict | None:
    _ensure_tables()
    with db() as cx:
        r = cx.execute(
            "SELECT * FROM debt_signals WHERE indicator_name=? ORDER BY timestamp DESC LIMIT 1",
            (name,),
        ).fetchone()
    return dict(r) if r else None


def get_latest_composite() -> dict | None:
    _ensure_tables()
    with db() as cx:
        r = cx.execute(
            "SELECT * FROM debt_composite ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
    return dict(r) if r else None


# ============================================================
# Scan orchestration
# ============================================================


def run_scan(tiers: list[int] | None = None, dispatch_alerts: bool = False) -> dict[str, Any]:
    """Fetch+classify+persist all indicators in given tiers (default all).

    If dispatch_alerts=True, sends Telegram notification on composite phase
    escalation OR any Tier 1 indicator transitioning to Phase 3+.
    """
    if tiers is None:
        tiers = [1, 2, 3]

    # Capture previous state BEFORE persist (for transition detection)
    prev_composite = get_latest_composite()
    prev_composite_phase = prev_composite["phase"] if prev_composite else None
    prev_indicator_phases: dict[str, int | None] = {}
    if dispatch_alerts:
        for name in INDICATOR_CONFIG:
            latest = get_latest_indicator(name)
            prev_indicator_phases[name] = latest["phase"] if latest else None

    results = {}
    breakdown_by_tier = {1: [], 2: [], 3: []}
    total_score = 0.0

    for name, cfg in INDICATOR_CONFIG.items():
        if cfg["tier"] not in tiers:
            # Use existing latest persisted value to keep composite continuous
            existing = get_latest_indicator(name)
            if existing and existing["phase"] is not None:
                contribution = _score_contribution(cfg["weight"], existing["phase"])
                total_score += contribution
                breakdown_by_tier[cfg["tier"]].append(
                    {"name": name, "value": existing["value"], "phase": existing["phase"],
                     "contribution": contribution, "stale": True}
                )
            continue

        value = fetch_indicator(name)
        if value is None:
            results[name] = {"value": None, "phase": None, "error": "fetch failed"}
            persist_signal(name, None, None)
            continue
        phase = classify_phase(value, cfg["phase_ranges"])
        persist_signal(name, value, phase)
        contribution = _score_contribution(cfg["weight"], phase)
        total_score += contribution
        results[name] = {"value": value, "phase": phase, "contribution": contribution}
        breakdown_by_tier[cfg["tier"]].append(
            {"name": name, "value": value, "phase": phase, "contribution": contribution}
        )

    overall_phase = composite_phase_from_score(total_score)
    persist_composite(total_score, overall_phase, breakdown_by_tier)
    result = {
        "score": total_score,
        "phase": overall_phase,
        "breakdown": breakdown_by_tier,
        "results": results,
    }
    if dispatch_alerts:
        _dispatch_alerts(result, prev_composite_phase, prev_indicator_phases)
    return result


# ============================================================
# Alert dispatch
# ============================================================

_PHASE_EMOJI = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
_PHASE_NAME = {1: "NORMAL", 2: "STRESS", 3: "SEVERE", 4: "CRISIS"}
_PHASE_ACTIONS = {
    1: "Monitor. No portfolio action required.",
    2: "Cash +5%, halt aggressive deploys, watch Tier 1 daily for escalation.",
    3: "Cash +10-15%, defensive rotation, trim leveraged or concentrated positions.",
    4: "Cash 25%+, kill leverage, hedge tail risk (puts/inverse), defensive only.",
}


def _alerts_enabled() -> bool:
    """Check bot_state.json debt_alerts_enabled flag. Fail-open (default True)."""
    try:
        from shared import storage
        state = storage.load_state()
        return bool(state.get("debt_alerts_enabled", True))
    except Exception:
        return True


def _dispatch_alerts(
    new_result: dict[str, Any],
    prev_composite_phase: int | None,
    prev_indicator_phases: dict[str, int | None],
) -> list[str]:
    """Build + send Telegram alerts on composite escalation or Tier 1 indicator transitioning to P3+.

    Behavior contract:
    - If _alerts_enabled() is False (via /debt_alerts off), returns [] without sending.
    - If prev_composite_phase is None (first-ever scan), no composite alert is sent
      (baseline establishment). Subsequent escalations from baseline trigger alerts.
    - Tier 1 indicator alerts fire only on fresh transition into P3+ (prev_p < 3 or None).
      Re-alerting suppressed while indicator persists at P3+ (deduplication).
    """
    if not _alerts_enabled():
        log.info("debt_monitor: alerts disabled via bot_state, skipping dispatch")
        return []

    from shared import notify

    new_phase = new_result["phase"]
    messages = []

    # 1. Composite phase escalation
    if prev_composite_phase is not None and new_phase > prev_composite_phase:
        prev_e = _PHASE_EMOJI[prev_composite_phase]
        prev_n = _PHASE_NAME[prev_composite_phase]
        new_e = _PHASE_EMOJI[new_phase]
        new_n = _PHASE_NAME[new_phase]
        urgency = "URGENT" if new_phase >= 3 else "WATCH"
        msg_lines = [
            f"*💣 DEBT MONITOR — {urgency}*",
            "",
            f"Composite: {prev_e} {prev_n} → {new_e} {new_n}",
            f"Score: {new_result['score']:.1f} pts (was Phase {prev_composite_phase})",
            "",
            "*Active stress drivers:*",
        ]
        for tier in [1, 2, 3]:
            for entry in new_result["breakdown"].get(tier, []):
                if entry.get("phase", 1) >= 2:
                    cfg = INDICATOR_CONFIG.get(entry["name"], {})
                    label = cfg.get("label", entry["name"])
                    val = entry.get("value")
                    val_s = (
                        "n/a" if val is None
                        else f"{val:,.0f}" if val >= 1000
                        else f"{val:.2f}" if val >= 1
                        else f"{val:.4f}"
                    )
                    p_e = _PHASE_EMOJI[entry["phase"]]
                    msg_lines.append(f"  {p_e} {label}: {val_s} (P{entry['phase']}, +{entry['contribution']:.1f}pts)")
        msg_lines.append("")
        msg_lines.append(f"*Action:* {_PHASE_ACTIONS[new_phase]}")
        msg_lines.append("")
        msg_lines.append("Run /debt_status for full breakdown.")
        messages.append("\n".join(msg_lines))

    # 2. Tier 1 individual indicator transitioning to Phase 3+
    for entry in new_result["breakdown"].get(1, []):
        name = entry["name"]
        new_p = entry.get("phase")
        prev_p = prev_indicator_phases.get(name)
        if new_p is None or new_p < 3:
            continue
        if prev_p is not None and prev_p >= 3:
            continue  # Already at P3+, no new transition
        cfg = INDICATOR_CONFIG.get(name, {})
        label = cfg.get("label", name)
        val = entry.get("value")
        val_s = (
            "n/a" if val is None
            else f"{val:,.0f}" if val >= 1000
            else f"{val:.2f}" if val >= 1
            else f"{val:.4f}"
        )
        p_e = _PHASE_EMOJI[new_p]
        messages.append(
            f"{p_e} *TIER 1 ALERT — {label}*\n\n"
            f"Value: {val_s}\n"
            f"Phase: {new_p} (was P{prev_p if prev_p is not None else '?'})\n\n"
            f"Single-indicator escalation. Run /debt_status."
        )

    # Dispatch all
    for m in messages:
        try:
            notify.send_text(m)
        except Exception as e:
            log.warning(f"alert dispatch failed: {e}")

    return messages


# ============================================================
# Cron wrappers (scheduler entry points)
# ============================================================


def cron_tier1_daily() -> None:
    """APScheduler entry: scan Tier 1 daily 06:00 Paris. Try/except envelope + crash alert."""
    _cron_run(tier=1, label="tier 1 daily")


def cron_tier2_weekly() -> None:
    """APScheduler entry: scan Tier 2 weekly Mon 06:30 Paris. Try/except envelope + crash alert."""
    _cron_run(tier=2, label="tier 2 weekly")


def cron_tier3_monthly() -> None:
    """APScheduler entry: scan Tier 3 monthly 1st 07:00 Paris. Try/except envelope + crash alert."""
    _cron_run(tier=3, label="tier 3 monthly")


def _cron_run(tier: int, label: str) -> None:
    """Shared cron pattern: try/except envelope + Telegram notify on crash.

    Aligns with bot/main.py existing cron pattern (try/except + log.exception + notify).
    Silent crashes break observability and the daily 06:00 protective layer.
    """
    try:
        log.info(f"debt_monitor: {label} starting")
        r = run_scan(tiers=[tier], dispatch_alerts=True)
        log.info(
            f"debt_monitor: {label} complete, composite phase {r['phase']} score {r['score']:.1f}"
        )
    except Exception as e:
        log.exception(f"debt_monitor: {label} cron crashed: {e}")
        try:
            from shared import notify
            notify.send_text(
                f"⚠️ *debt_monitor {label}* cron crashed\n\n"
                f"`{type(e).__name__}: {e}`\n\n"
                f"Bot continues. Next attempt next cycle. Investigate logs."
            )
        except Exception as alert_err:
            log.warning(f"debt_monitor: crash-alert dispatch failed: {alert_err}")


def status_snapshot() -> dict[str, Any]:
    """Read latest persisted state without fetching (cheap for /debt_status)."""
    _ensure_tables()
    composite = get_latest_composite()
    indicators = {}
    for name in INDICATOR_CONFIG:
        latest = get_latest_indicator(name)
        if latest:
            indicators[name] = latest
    return {"composite": composite, "indicators": indicators}


if __name__ == "__main__":
    print("=== Debt Crisis Monitor — full scan ===")
    r = run_scan()
    print(f"Composite score: {r['score']:.1f}  Phase: {r['phase']}")
    for tier in [1, 2, 3]:
        print(f"\n--- Tier {tier} ---")
        for entry in r["breakdown"][tier]:
            stale = " [stale]" if entry.get("stale") else ""
            val = entry.get("value")
            if val is None:
                val_s = "n/a"
            elif abs(val) < 1:
                val_s = f"{val:.4f}"
            elif val >= 1000:
                val_s = f"{val:,.0f}"
            else:
                val_s = f"{val:.2f}"
            print(f"  {entry['name']:14} {val_s:>12} phase={entry['phase']} +{entry['contribution']:.1f}pts{stale}")
