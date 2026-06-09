"""#130 — Perf watch : timings clés du système + alertes si dégradation.

Cf clôture session 09/06 (Olivier) : 'regen 45s / refresh 60s marge fine,
surveiller quand le ledger grossit'. Ce script trace les timings critiques
et alerte si seuils dépassés.

Usage :
  python3 scripts/perf_watch.py              # check + tableau
  python3 scripts/perf_watch.py --json       # output JSON pour CI
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import contextmanager


@contextmanager
def _timed(label: str, store: dict):
    t0 = time.perf_counter()
    yield
    store[label] = (time.perf_counter() - t0) * 1000  # ms


# Seuils alerte (ms). Au-dessus = warning, 2x = critical.
THRESHOLDS = {
    "vue_select_all": (100, 500),         # VUE positions SELECT * (cible <100ms)
    "compute_pmp_per_ticker": (5, 20),    # helper rolling (cible <5ms/ticker)
    "load_db_positions": (200, 1000),     # _load_db_positions complet
    "get_held_lines_warm": (200, 1000),   # avec cache warm
    "dashboard_render": (40000, 50000),   # 40s seuil, 50s critical (cron 60s)
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-render", action="store_true", help="Skip dashboard render (slow)")
    args = ap.parse_args()

    timings: dict = {}

    # 1. VUE SQL pur
    import sqlite3
    cx = sqlite3.connect("data/bot.db")
    with _timed("vue_select_all", timings):
        rows = cx.execute("SELECT * FROM positions WHERE qty > 0").fetchall()
    timings["vue_n_positions"] = len(rows)

    # 2. compute_pmp_realized helper (sample 3 tickers)
    from shared.ledger_pmp import compute_pmp_realized
    sample_tickers = [r[1] for r in rows[:3]]  # 3 first tickers
    with _timed("compute_pmp_3_tickers", timings):
        for tk in sample_tickers:
            compute_pmp_realized(cx, tk)
    timings["compute_pmp_per_ticker"] = timings["compute_pmp_3_tickers"] / max(len(sample_tickers), 1)
    cx.close()

    # 3. _load_db_positions
    from shared.book import _load_db_positions
    with _timed("load_db_positions", timings):
        _load_db_positions()

    # 4. get_held_lines warm (run twice — 2nd is cached)
    from shared.book import get_held_lines
    with _timed("get_held_lines_cold", timings):
        get_held_lines()
    with _timed("get_held_lines_warm", timings):
        get_held_lines()

    # 5. Dashboard render (skippable)
    if not args.skip_render:
        from dashboard import render
        with _timed("dashboard_render", timings):
            render.render()

    # Compute verdict
    alerts = []
    for key, (warn, crit) in THRESHOLDS.items():
        val = timings.get(key)
        if val is None:
            continue
        if val > crit:
            alerts.append(f"CRITICAL {key}={val:.1f}ms > {crit}ms")
        elif val > warn:
            alerts.append(f"WARN     {key}={val:.1f}ms > {warn}ms")

    if args.json:
        out = {"timings_ms": timings, "alerts": alerts}
        print(json.dumps(out, indent=2))
    else:
        print(f"=== perf_watch — {timings.get('vue_n_positions', 0)} positions ===")
        for k, v in sorted(timings.items()):
            warn, crit = THRESHOLDS.get(k, (None, None))
            tag = ""
            if isinstance(v, (int, float)) and warn is not None:
                if v > crit:
                    tag = " ⚠ CRITICAL"
                elif v > warn:
                    tag = " ⚠ WARN"
                else:
                    tag = " ✓"
            print(f"  {k:30s} {v:>10.1f}{tag}")
        print()
        if alerts:
            print("Alerts :")
            for a in alerts:
                print(f"  {a}")
        else:
            print("✓ Tous les timings sous seuils")

    return 1 if any("CRITICAL" in a for a in alerts) else 0


if __name__ == "__main__":
    sys.exit(main())
