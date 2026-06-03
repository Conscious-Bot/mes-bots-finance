"""Historical timeseries pour track record (charts publics).

Fonctions helper qui retournent des points {date, value} pour rendre
des charts (Brier rolling, bias cumul, predictions volume). Sans ces
helpers, impossible de visualiser une evolution -- juste des snapshots.

Patterns :
- date au format ISO ('YYYY-MM-DD')
- value None autorise quand insufficient data sur la fenetre
- liste trie croissant par date
- granularite definie par step_days (default weekly)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any

from shared import storage


def _date_range(total_days: int, step_days: int, end_date: date | None = None) -> list[date]:
    """Liste des dates ancrees (les end-of-period) du window total_days
    par pas de step_days. Plus recent en dernier."""
    if end_date is None:
        end_date = datetime.now(UTC).date()
    points = []
    cur = end_date
    while (end_date - cur).days < total_days:
        points.append(cur)
        cur = cur - timedelta(days=step_days)
    return list(reversed(points))


def compute_brier_rolling_timeseries(
    cx: sqlite3.Connection,
    window_days: int = 30,
    total_days: int = 180,
    step_days: int = 7,
) -> list[dict[str, Any]]:
    """Brier moyen rolling window pour chaque point d'echantillonnage.

    Args:
        cx: sqlite3 connection
        window_days: largeur de la fenetre (default 30j)
        total_days: span total de l'historique (default 180j)
        step_days: pas entre points (default 7j weekly)

    Returns:
        [{date, brier_avg, n_resolved, accuracy_pct}, ...] trie chrono.
        brier_avg = None si n_resolved < 3 sur la fenetre.
    """
    out = []
    for d in _date_range(total_days, step_days):
        window_start = (d - timedelta(days=window_days)).isoformat()
        window_end = d.isoformat()
        row = cx.execute(
            "SELECT AVG(brier_score) AS b, COUNT(*) AS n, "
            "       SUM(CASE WHEN outcome='correct' THEN 1 ELSE 0 END) AS nc "
            "FROM predictions "
            f"WHERE {storage.canonical_predictions_filter()} "
            "AND resolved_at >= ? AND resolved_at < ? "
            "AND brier_score IS NOT NULL "
            "AND outcome IN ('correct', 'incorrect')",
            (window_start, window_end),
        ).fetchone()
        n = int(row[1] or 0)
        brier = float(row[0]) if (row[0] is not None and n >= 3) else None
        nc = int(row[2] or 0)
        acc = round(nc / n * 100, 1) if n > 0 and brier is not None else None
        out.append({
            "date": window_end,
            "brier_avg": round(brier, 4) if brier is not None else None,
            "n_resolved": n,
            "accuracy_pct": acc,
        })
    return out


def compute_bias_cumul_timeseries(
    cx: sqlite3.Connection,
    bias: str,
    total_days: int = 180,
    step_days: int = 7,
) -> list[dict[str, Any]]:
    """Cumul delta_signed_eur par bias sur l'historique (running total).

    Args:
        bias: 'lock_in' / 'fomo_greed' / 'other'
        total_days: span historique
        step_days: pas weekly

    Returns:
        [{date, cumul_delta_eur, n_resolved_to_date}, ...] trie chrono.
    """
    # Pull tous les events resolved du bias avec resolution_json
    rows = cx.execute(
        "SELECT created_at, resolution_json FROM bias_events "
        "WHERE bias = ? AND status = 'resolved' "
        "ORDER BY id ASC",
        (bias,),
    ).fetchall()
    # Parse + collect (resolved_at, delta) tuples
    events: list[tuple[str, float]] = []
    for r in rows:
        rj = r[1]
        if not rj:
            continue
        try:
            d = json.loads(rj)
        except (json.JSONDecodeError, TypeError):
            continue
        delta = d.get("delta_signed_eur")
        resolved_at = d.get("resolved_at") or r[0]
        if delta is None or not resolved_at:
            continue
        try:
            events.append((str(resolved_at)[:10], float(delta)))
        except (ValueError, TypeError):
            continue
    events.sort(key=lambda x: x[0])

    out = []
    cumul = 0.0
    n_to_date = 0
    idx = 0
    for d in _date_range(total_days, step_days):
        d_iso = d.isoformat()
        while idx < len(events) and events[idx][0] <= d_iso:
            cumul += events[idx][1]
            n_to_date += 1
            idx += 1
        out.append({
            "date": d_iso,
            "cumul_delta_eur": round(cumul, 2),
            "n_resolved_to_date": n_to_date,
        })
    return out


def compute_predictions_volume_timeseries(
    cx: sqlite3.Connection,
    total_days: int = 180,
    step_days: int = 7,
) -> list[dict[str, Any]]:
    """Volume predictions creees par fenetre (weekly counts).

    Returns:
        [{date, n_created_in_window, n_resolved_in_window}, ...]
    """
    out = []
    for d in _date_range(total_days, step_days):
        window_start = (d - timedelta(days=step_days)).isoformat()
        window_end = d.isoformat()
        row_c = cx.execute(
            "SELECT COUNT(*) FROM predictions "
            f"WHERE {storage.canonical_predictions_filter()} "
            "AND baseline_date >= ? AND baseline_date < ?",
            (window_start, window_end),
        ).fetchone()
        row_r = cx.execute(
            "SELECT COUNT(*) FROM predictions "
            f"WHERE {storage.canonical_predictions_filter()} "
            "AND resolved_at >= ? AND resolved_at < ?",
            (window_start, window_end),
        ).fetchone()
        out.append({
            "date": window_end,
            "n_created_in_window": int(row_c[0] or 0),
            "n_resolved_in_window": int(row_r[0] or 0),
        })
    return out


def compute_all_timeseries(
    cx: sqlite3.Connection,
    total_days: int = 180,
    step_days: int = 7,
) -> dict[str, list[dict[str, Any]]]:
    """Bundle : retourne les 3 timeseries canoniques + bias par type."""
    return {
        "brier_rolling": compute_brier_rolling_timeseries(
            cx, total_days=total_days, step_days=step_days,
        ),
        "predictions_volume": compute_predictions_volume_timeseries(
            cx, total_days=total_days, step_days=step_days,
        ),
        "bias_cumul_lock_in": compute_bias_cumul_timeseries(
            cx, "lock_in", total_days=total_days, step_days=step_days,
        ),
        "bias_cumul_fomo_greed": compute_bias_cumul_timeseries(
            cx, "fomo_greed", total_days=total_days, step_days=step_days,
        ),
    }
