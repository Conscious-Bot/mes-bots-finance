"""Monitors summary — unified read of live monitor state for surface display.

3 surfaces consume this helper (single source) :
1. Telegram daily digest (bot/jobs/daily.py:daily_digest_job)
2. Dashboard Overview top band (dashboard/render.py:_vigie)
3. Cerebro accordion (dashboard/render.py:_vault)

Pattern : helper pure-fonction lit DB live, retourne dict structured.
Aucune décision, aucune action, juste extraction.

Doctrine 26/06 (post red-teams) : les monitors TIRENT déjà via cron
(morning_chain + 7h stress_gate cron) mais leurs signaux restent dans
les journaux append-only over_cap_alerts / stress_gate_alerts. Cette
fonction REMONTE l'essentiel à la surface user-visible.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def get_monitors_summary() -> dict[str, Any]:
    """Returns {
        'over_cap': {...},
        'stress_gate': {...},
        'kill_criteria': {...},
        'stale_target': {...},
        'benchmark': {'w30': {...}, 'w90': {...}},  # Tier 2 #5 wiring 26/06
    }

    Fail-soft : chaque section retourne valeurs vides si table absente / query fail.
    """
    from shared import storage

    out = {
        "over_cap": {"over_count": 0, "today_transitions": [], "over_tickers": []},
        "stress_gate": {"worst_scenario": None, "breached_scenarios": []},
        "kill_criteria": {"triggered_tickers": [], "at_risk_tickers": []},
        "stale_target": {"dead_tickers": [], "dying_tickers": []},
        "benchmark": {"w30": None, "w90": None},
    }

    # 1. over_cap — current 'over' positions + today's dormant→over transitions
    try:
        with storage.db() as cx:
            rows = cx.execute("""
                SELECT ticker, status, transition, weight_pct, cap_pct, datetime(created_at) as ts
                FROM over_cap_alerts
                WHERE id IN (
                    SELECT MAX(id) FROM over_cap_alerts GROUP BY ticker
                )
                ORDER BY weight_pct DESC
            """).fetchall()
            over_tickers = []
            for r in rows:
                tk, status, transition, w, cap, ts = r
                if status == "over":
                    over_tickers.append(tk)
                if transition == "dormant_to_over" and ts and ts.startswith(_today_iso()):
                    out["over_cap"]["today_transitions"].append({
                        "ticker": tk, "transition": transition,
                        "weight_pct": round(w, 2), "cap_pct": cap,
                    })
            out["over_cap"]["over_tickers"] = over_tickers
            out["over_cap"]["over_count"] = len(over_tickers)
    except Exception as e:
        log.debug(f"over_cap summary fail: {e}")

    # 2. stress_gate — worst scenario today by drawdown_pct
    try:
        with storage.db() as cx:
            rows = cx.execute("""
                SELECT scenario_name, status, drawdown_pct, warn_pct, breach_pct
                FROM stress_gate_alerts
                WHERE id IN (SELECT MAX(id) FROM stress_gate_alerts GROUP BY scenario_name)
                ORDER BY drawdown_pct ASC
            """).fetchall()
            if rows:
                worst = rows[0]
                out["stress_gate"]["worst_scenario"] = {
                    "scenario_name": worst[0], "status": worst[1],
                    "drawdown_pct": round(worst[2], 1),
                    "warn_pct": worst[3], "breach_pct": worst[4],
                }
                for r in rows:
                    if r[1] in ("warn", "breach"):
                        out["stress_gate"]["breached_scenarios"].append({
                            "scenario_name": r[0], "status": r[1],
                            "drawdown_pct": round(r[2], 1),
                        })
    except Exception as e:
        log.debug(f"stress_gate summary fail: {e}")

    # 3. kill_criteria — current triggered + at_risk theses
    try:
        with storage.db() as cx:
            rows = cx.execute("""
                SELECT t.ticker, t.kill_criteria_status
                FROM theses t
                WHERE t.status='active'
                  AND t.kill_criteria_status IN ('triggered', 'at_risk')
                ORDER BY
                    CASE t.kill_criteria_status WHEN 'triggered' THEN 0 ELSE 1 END,
                    t.ticker
            """).fetchall()
            for tk, status in rows:
                if status == "triggered":
                    out["kill_criteria"]["triggered_tickers"].append(tk)
                elif status == "at_risk":
                    out["kill_criteria"]["at_risk_tickers"].append(tk)
    except Exception as e:
        log.debug(f"kill_criteria summary fail: {e}")

    # 4. stale_target — current dying / dead theses
    try:
        with storage.db() as cx:
            rows = cx.execute("""
                SELECT ticker, status
                FROM stale_target_alerts
                WHERE id IN (SELECT MAX(id) FROM stale_target_alerts GROUP BY ticker)
                  AND status IN ('dying', 'dead')
            """).fetchall()
            for tk, status in rows:
                if status == "dead":
                    out["stale_target"]["dead_tickers"].append(tk)
                else:
                    out["stale_target"]["dying_tickers"].append(tk)
    except Exception as e:
        log.debug(f"stale_target summary fail: {e}")

    # 5. benchmark vs SMH/SPY/QQQ — Tier 2 #5 wiring (26/06)
    try:
        from intelligence.benchmark_tracker import get_benchmarks_summary
        bm = get_benchmarks_summary()
        out["benchmark"] = bm
    except Exception as e:
        log.debug(f"benchmark summary fail: {e}")

    return out


def format_text_summary(summary: dict[str, Any] | None = None) -> str:
    """Format summary en bloc texte court pour Telegram digest matin.

    Format compact (max ~10 lignes) : ne montre que ce qui mérite attention.
    Skip les sections vides.
    """
    if summary is None:
        summary = get_monitors_summary()

    parts = []

    # over_cap
    oc = summary["over_cap"]
    if oc["today_transitions"]:
        for t in oc["today_transitions"]:
            parts.append(f"🔺 OVER_CAP {t['ticker']} : {t['weight_pct']}% (cap {t['cap_pct']}%) [today]")
    elif oc["over_tickers"]:
        parts.append(f"🔸 over_cap actuel : {', '.join(oc['over_tickers'])}")

    # stress_gate
    sg = summary["stress_gate"]
    if sg["breached_scenarios"]:
        for s in sg["breached_scenarios"]:
            parts.append(f"⚠️ STRESS {s['scenario_name']} : drawdown {s['drawdown_pct']}% [{s['status']}]")
    elif sg["worst_scenario"]:
        w = sg["worst_scenario"]
        parts.append(f"🔹 worst stress : {w['scenario_name']} {w['drawdown_pct']}% (warn {w['warn_pct']}%)")

    # kill_criteria
    kc = summary["kill_criteria"]
    if kc["triggered_tickers"]:
        parts.append(f"🚨 KILL TRIGGERED : {', '.join(kc['triggered_tickers'])}")
    if kc["at_risk_tickers"]:
        parts.append(f"⚠ kill at_risk : {', '.join(kc['at_risk_tickers'])}")

    # stale_target
    st = summary["stale_target"]
    if st["dead_tickers"]:
        parts.append(f"💀 stale DEAD : {', '.join(st['dead_tickers'])}")
    if st["dying_tickers"]:
        parts.append(f"💭 stale dying : {', '.join(st['dying_tickers'])}")

    # benchmark (Tier 2 #5, 26/06) — affiche delta SMH 30d primary
    bm = summary.get("benchmark") or {}
    w30 = bm.get("w30") or {}
    if w30.get("ok"):
        bms = w30.get("benchmarks") or {}
        pr_pct = w30.get("portfolio_return_pct", 0)
        smh = bms.get("SMH")
        spy = bms.get("SPY")
        qqq = bms.get("QQQ")
        bench_segs = []
        if smh:
            bench_segs.append(f"SMH Δ{smh['delta_pp']:+.1f}pp")
        if spy:
            bench_segs.append(f"SPY Δ{spy['delta_pp']:+.1f}pp")
        if qqq:
            bench_segs.append(f"QQQ Δ{qqq['delta_pp']:+.1f}pp")
        if bench_segs:
            parts.append(f"📈 Portfolio 30j {pr_pct:+.2f}% · " + " · ".join(bench_segs))

    if not parts:
        return "📊 Monitors : tout sain (over_cap=0, stress=ok, kill_criteria=0, stale=0)"

    return "📊 MONITORS LIVE\n" + "\n".join(parts)


def _today_iso() -> str:
    import datetime
    return datetime.date.today().isoformat()
