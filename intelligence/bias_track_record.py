"""Bias track record : agregation outcome bias_events par type.

Boucle prediction -> learning -> tracking -> theses :
ce module agrege les `bias_events` resolved par type de biais pour
exposer le cumul `delta_signed_eur` (cout ou benefice de la discipline).

Convention delta_signed_eur (spec Surface 2 02/06) :
  - lock_in : negatif = prix monte apres vente = cout (money left on table)
              positif = prix baisse apres vente = exit sage
  - fomo_greed : negatif = "j'aurais du trim" non fait, cout subi
              positif = "discipline aurait dit trim" mais hold a paye
  - other : convention agnostique, signe brut

Cumul EUR = somme algebrique des delta_signed_eur. Negatif = la
discipline coute en cumul (le user ignore les triggers). Positif = la
discipline epargne (le user suit les triggers).

Sans ce module, presage.pro/track ne peut pas exposer le cout/benefice
concret en EUR de la mecanique anti-biais.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _parse_delta(resolution_json: str | None) -> float | None:
    """Extract delta_signed_eur du resolution_json. None si parsing fail
    ou clé manquante."""
    if not resolution_json:
        return None
    try:
        d = json.loads(resolution_json)
        v = d.get("delta_signed_eur")
        return float(v) if v is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def compute_bias_track_record(
    cx: sqlite3.Connection,
    bias: str,
    rolling_days: int | None = None,
) -> dict[str, Any]:
    """Aggregation outcomes per bias type.

    Args:
        cx: connexion sqlite3
        bias: 'lock_in' / 'fomo_greed' / 'other'
        rolling_days: optionnel, restreint aux events resolved depuis N j

    Returns:
        dict :
            bias (str)
            n_open, n_resolved, n_void, n_missing_data
            total_delta_signed_eur (sum)
            avg_delta_eur (None si n_resolved=0)
            median_delta_eur, p95_delta_eur (None si n_resolved < 5)
            fraction_harmful (% delta < 0)
            fraction_beneficial (% delta > 0)
            latest_resolved (dict {ticker, delta_signed_eur, resolved_at}
                             ou None)
            posture : 'OK' (delta_total > 0 sustained) / 'WARN' /
                      'ALERT' (delta_total < seuil) /
                      'INSUFFICIENT_DATA' (n_resolved < 3)
    """
    base_query = (
        "SELECT id, ticker, status, resolution_json "
        "FROM bias_events WHERE bias = ?"
    )
    params: list[Any] = [bias]
    if rolling_days is not None:
        base_query += " AND created_at >= datetime('now', ?)"
        params.append(f"-{rolling_days} days")

    rows = cx.execute(base_query, params).fetchall()

    n_open = 0
    n_resolved = 0
    n_void = 0
    n_missing = 0
    deltas: list[tuple[str, float, str]] = []  # (ticker, delta, status)
    latest: dict[str, Any] | None = None

    # Query separee pour latest (avec resolved_at sort)
    latest_query = (
        "SELECT id, ticker, resolution_json, status FROM bias_events "
        "WHERE bias = ? AND status = 'resolved' "
        "ORDER BY id DESC LIMIT 1"
    )
    latest_row = cx.execute(latest_query, (bias,)).fetchone()
    if latest_row:
        if isinstance(latest_row, dict):
            lr = latest_row
        else:
            lr = {
                "id": latest_row[0], "ticker": latest_row[1],
                "resolution_json": latest_row[2], "status": latest_row[3],
            }
        delta = _parse_delta(lr.get("resolution_json"))
        try:
            resj = json.loads(lr.get("resolution_json") or "{}")
            resolved_at = resj.get("resolved_at")
        except (json.JSONDecodeError, TypeError):
            resolved_at = None
        latest = {
            "ticker": lr.get("ticker"),
            "delta_signed_eur": delta,
            "resolved_at": resolved_at,
        }

    for r in rows:
        if isinstance(r, dict):
            row = r
        else:
            row = {
                "id": r[0], "ticker": r[1], "status": r[2],
                "resolution_json": r[3],
            }
        status = row.get("status")
        if status == "open":
            n_open += 1
        elif status == "resolved":
            n_resolved += 1
            delta = _parse_delta(row.get("resolution_json"))
            if delta is not None:
                deltas.append((row.get("ticker") or "", float(delta), status))
        elif status in ("void", "thesis_invalidated", "reentered"):
            n_void += 1
        elif status == "missing_data":
            n_missing += 1

    # Stats
    delta_values = [d for _, d, _ in deltas]
    total_delta = sum(delta_values) if delta_values else 0.0
    avg_delta = (total_delta / len(delta_values)) if delta_values else None

    median_delta = None
    p95_delta = None
    if len(delta_values) >= 5:
        sorted_d = sorted(delta_values)
        median_delta = sorted_d[len(sorted_d) // 2]
        p95_idx = int(len(sorted_d) * 0.95)
        p95_delta = sorted_d[min(p95_idx, len(sorted_d) - 1)]

    n_harmful = sum(1 for d in delta_values if d < 0)
    n_beneficial = sum(1 for d in delta_values if d > 0)
    fraction_harmful = (
        round(n_harmful / len(delta_values), 3) if delta_values else None
    )
    fraction_beneficial = (
        round(n_beneficial / len(delta_values), 3) if delta_values else None
    )

    # Posture
    if len(delta_values) < 3:
        posture = "INSUFFICIENT_DATA"
    elif total_delta >= 0 and fraction_beneficial is not None and fraction_beneficial >= 0.5:
        posture = "OK"
    elif total_delta < -500:  # -500 EUR cumule sur N >= 3 = signal d'erosion
        posture = "ALERT"
    else:
        posture = "WARN"

    return {
        "bias": bias,
        "n_open": n_open,
        "n_resolved": n_resolved,
        "n_void": n_void,
        "n_missing_data": n_missing,
        "total_delta_signed_eur": round(total_delta, 2),
        "avg_delta_eur": round(avg_delta, 2) if avg_delta is not None else None,
        "median_delta_eur": round(median_delta, 2) if median_delta is not None else None,
        "p95_delta_eur": round(p95_delta, 2) if p95_delta is not None else None,
        "fraction_harmful": fraction_harmful,
        "fraction_beneficial": fraction_beneficial,
        "latest_resolved": latest,
        "posture": posture,
    }


def compute_all_bias_track_records(
    cx: sqlite3.Connection,
    rolling_days: int | None = None,
) -> list[dict[str, Any]]:
    """Track record pour les 3 bias types canoniques."""
    return [
        compute_bias_track_record(cx, b, rolling_days=rolling_days)
        for b in ("lock_in", "fomo_greed", "other")
    ]
