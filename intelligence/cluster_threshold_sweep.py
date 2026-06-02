"""#78 LOOP -- Insider cluster threshold sweep (ADR-013 validation).

Probleme : on declenche signal/prediction sur insider_buy_cluster si
n_buyers >= 3 AND total_m >= 1.0 (cf shared.edgar._classify_buy_cluster).
Ces seuils sont *a priori*, pas valides empiriquement. ADR-013 a deferred
l'optimisation faute de data historique.

Solution : helper qui ACCEPTE un dataset de clusters resolved (avec
return forward J+30/J+90) + balaie une grille de seuils, calcule pour
chaque seuil les KPIs (n_above_threshold, mean_return, sharpe, Wilson
IC95 sur positive_rate), retourne le seuil optimal.

Decouple la **mecanique du sweep** (testable maintenant) du **data
acquisition** (a accumuler via cron sur les prochaines semaines).

Usage post J+30/N=20 :
    from intelligence.cluster_threshold_sweep import (
        sweep_thresholds, find_optimal_threshold,
    )
    clusters = pull_resolved_clusters(cx, days=365)  # accumule via prod
    grid = [{'min_n': n, 'min_m': m} for n in [2,3,4,5] for m in [0.5, 1, 2, 5]]
    sweep = sweep_thresholds(clusters, grid, horizon='30d')
    optimal = find_optimal_threshold(sweep, min_n_signals=10)
"""

from __future__ import annotations

import math
from typing import Any


def _wilson_ic95(n_correct: int, n_total: int) -> tuple[float, float]:
    """Wilson IC95 sur p = correct/total."""
    if n_total == 0:
        return 0.0, 1.0
    p = n_correct / n_total
    z = 1.96
    denom = 1 + z * z / n_total
    center = (n_correct + z * z / 2) / n_total / denom
    half = z * math.sqrt(p * (1 - p) / n_total + z * z / (4 * n_total * n_total)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _cluster_meets_threshold(cluster: dict, threshold: dict) -> bool:
    """Verifie si un cluster satisfait un seuil composite."""
    n = cluster.get("distinct_buyers", 0) or 0
    m = cluster.get("total_buy_m", 0.0) or 0.0
    min_n = threshold.get("min_n", 1)
    min_m = threshold.get("min_m", 0.0)
    return n >= min_n and m >= min_m


def sweep_thresholds(
    clusters: list[dict],
    threshold_grid: list[dict],
    horizon: str = "30d",
) -> list[dict[str, Any]]:
    """Balaye une grille de seuils sur le dataset clusters.

    Args:
        clusters: liste de dicts avec au minimum :
            {distinct_buyers (int), total_buy_m (float),
             return_30d (float|None), return_90d (float|None)}
        threshold_grid: liste de dicts {min_n, min_m, ...}
        horizon: '30d' ou '90d' (column return_<horizon>)

    Returns:
        Liste de dicts par seuil :
            threshold, n_total_above, n_resolved (return non-None),
            mean_return, median_return, sharpe (mean/std ou None si std=0),
            positive_rate, ic95_low, ic95_high,
            status : 'INSUFFICIENT_DATA' (n<5) / 'OK' (sharpe>0.5) /
                     'WARN' (sharpe<0.5 ou positive_rate<0.55) /
                     'ALERT' (mean_return<0)
    """
    if horizon not in ("30d", "90d"):
        raise ValueError(f"horizon must be '30d' or '90d', got {horizon!r}")
    return_key = f"return_{horizon}"

    out = []
    for thr in threshold_grid:
        above = [c for c in clusters if _cluster_meets_threshold(c, thr)]
        resolved = [
            float(c[return_key])
            for c in above
            if c.get(return_key) is not None
        ]
        n_total = len(above)
        n_resolved = len(resolved)

        if n_resolved == 0:
            out.append({
                "threshold": thr,
                "n_total_above": n_total,
                "n_resolved": 0,
                "mean_return": None,
                "median_return": None,
                "sharpe": None,
                "positive_rate": None,
                "ic95_low": None,
                "ic95_high": None,
                "status": "INSUFFICIENT_DATA",
            })
            continue

        mean_r = sum(resolved) / n_resolved
        sorted_r = sorted(resolved)
        median_r = sorted_r[n_resolved // 2]
        if n_resolved > 1:
            variance = sum((r - mean_r) ** 2 for r in resolved) / (n_resolved - 1)
            std_r = math.sqrt(variance)
            sharpe = mean_r / std_r if std_r > 1e-9 else None
        else:
            sharpe = None

        n_positive = sum(1 for r in resolved if r > 0)
        positive_rate = n_positive / n_resolved
        ic_lo, ic_hi = _wilson_ic95(n_positive, n_resolved)

        if n_resolved < 5:
            status = "INSUFFICIENT_DATA"
        elif mean_r < 0:
            status = "ALERT"
        elif sharpe is not None and sharpe < 0.5:
            status = "WARN"
        elif positive_rate < 0.55:
            status = "WARN"
        else:
            status = "OK"

        out.append({
            "threshold": thr,
            "n_total_above": n_total,
            "n_resolved": n_resolved,
            "mean_return": round(mean_r, 4),
            "median_return": round(median_r, 4),
            "sharpe": round(sharpe, 3) if sharpe is not None else None,
            "positive_rate": round(positive_rate, 3),
            "ic95_low": round(ic_lo, 3),
            "ic95_high": round(ic_hi, 3),
            "status": status,
        })
    return out


def find_optimal_threshold(
    sweep_results: list[dict[str, Any]],
    min_n_signals: int = 10,
    criterion: str = "sharpe",
) -> dict[str, Any] | None:
    """Selectionne le seuil optimal selon un critere.

    Args:
        sweep_results: output de sweep_thresholds
        min_n_signals: filtre n_resolved minimum (sinon sur-fit small N)
        criterion: 'sharpe' / 'mean_return' / 'positive_rate'

    Returns:
        Le dict de sweep_results qui maximise le critere parmi ceux
        avec n_resolved >= min_n_signals. None si aucun candidat.
    """
    if criterion not in ("sharpe", "mean_return", "positive_rate"):
        raise ValueError(f"criterion invalide : {criterion!r}")

    candidates = [
        r for r in sweep_results
        if r["n_resolved"] >= min_n_signals
        and r.get(criterion) is not None
        and r["status"] != "ALERT"
    ]
    if not candidates:
        return None

    return max(candidates, key=lambda r: r[criterion])


def default_threshold_grid() -> list[dict[str, Any]]:
    """Grille canonique pour le sweep. Couvre la zone realiste.

    n in {2, 3, 4, 5, 6} (actuel = 3 -- voir si 4 ou 5 fait mieux)
    m in {0.5, 1.0, 2.0, 5.0, 10.0} M$ (actuel = 1.0 -- voir si 2 ou 5 fait mieux)
    """
    return [
        {"min_n": n, "min_m": m}
        for n in (2, 3, 4, 5, 6)
        for m in (0.5, 1.0, 2.0, 5.0, 10.0)
    ]
