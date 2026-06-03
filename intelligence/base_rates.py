"""base_rates -- bibliotheque de taux de base empiriques pour nourrir le scorer.

Strategie user 31/05/2026 point #3b : "Bibliotheque de base rates empiriques :
nourris le scorer de vrais taux de base (depuis ta data / l'historique) au
lieu de ceux qu'il devine. L'outside view de Tetlock, operationnalisee --
gros levier de calibration."

Architecture :
- Compute : agrege depuis predictions resolues + signals historiques
  (groupBy signal_type, direction, horizon_days bucket). Wilson CI.
- Lookup : api simple `get_empirical_base_rate(signal_type, direction,
  horizon_days, threshold_pct)` retourne dict {rate, n, ci_lo, ci_hi, as_of}
  ou None si bucket vide.
- Injection : signal_scorer_v2 lit la base rate avant elicitation pour
  donner au LLM la vraie statistique au lieu de la lui faire deviner.

Activation : MIN_N_PER_BUCKET = 10 predictions par (signal_type, direction,
horizon_bucket). Avant ce seuil : retourne None (le scorer doit fallback
sur son estimate). Au-dela : retourne le taux empirique avec Wilson CI.

Integration : appele depuis intelligence/signal_scorer_v2.py au step 1 du
prompt (BASE RATE) -- au lieu de demander au LLM "qu'est-ce que ton intuition
te dit ?", on lui donne "voici la stat empirique : 12% +/- 5% sur N=45 cas
similaires" et on lui demande d'ajuster a partir de la. Pas branche en J0
(scaffolding), s'activera bucket-by-bucket quand chaque bucket atteint N=10.

Discipline (CONVENTIONS.md) :
- Wilson CI obligatoire (jamais point estimate seul)
- Refus de servir base rate si n < MIN_N_PER_BUCKET
- Dedup implicite via UNIQUE constraint signals.gmail_id (deja en place)
"""

from __future__ import annotations

import logging
import math
import sqlite3
from typing import Any

from shared import storage

log = logging.getLogger(__name__)

MIN_N_PER_BUCKET = 10
HORIZON_BUCKETS = [(1, 7), (8, 14), (15, 30), (31, 60), (61, 365)]


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI. Identique a calibration_audit._wilson_ci."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _horizon_bucket(horizon_days: int) -> tuple[int, int] | None:
    """Quel bucket pour ce horizon. None si hors range."""
    for lo, hi in HORIZON_BUCKETS:
        if lo <= horizon_days <= hi:
            return (lo, hi)
    return None


def get_empirical_base_rate(
    cx: sqlite3.Connection,
    signal_type: str | None,
    direction: str,
    horizon_days: int,
) -> dict[str, Any] | None:
    """Taux empirique de "prediction correcte" pour ce type de signal/direction/horizon.

    Args:
        cx : sqlite3 connection
        signal_type : 'earnings', 'insider_cluster', '8K', etc. None = all types
        direction : 'bullish' ou 'bearish'
        horizon_days : utilise pour assigner un bucket horizon

    Returns:
        {
            "rate": float in [0,1],
            "n": int,
            "ci_lo": float, "ci_hi": float,
            "horizon_bucket": (lo, hi) or None,
            "as_of": ISO datetime str,
            "signal_type": str or None,
            "direction": str,
        }
        ou None si bucket vide ou n < MIN_N_PER_BUCKET.
    """
    bucket = _horizon_bucket(horizon_days)
    if bucket is None:
        log.info(f"base_rate : horizon={horizon_days} hors buckets, skip")
        return None
    lo, hi = bucket
    params: list = [lo, hi, direction]
    where_signal = ""
    if signal_type is not None:
        where_signal = "AND signal_type = ? "
        params.append(signal_type)

    rows = cx.execute(
        f"""
        SELECT outcome
        FROM predictions
        WHERE resolved_at IS NOT NULL
          AND outcome IN ('correct', 'incorrect')
          AND {storage.substance_predictions_filter()}
          AND direction = ?
          AND horizon_days BETWEEN ? AND ?
          {where_signal}
        """,
        [direction, lo, hi] + ([signal_type] if signal_type else []),
    ).fetchall()
    n = len(rows)
    if n < MIN_N_PER_BUCKET:
        log.info(
            f"base_rate : n={n} < MIN_N_PER_BUCKET={MIN_N_PER_BUCKET} "
            f"pour signal_type={signal_type} direction={direction} "
            f"horizon={lo}-{hi}, skip"
        )
        return None
    k_correct = sum(1 for r in rows if r[0] == "correct")
    rate = k_correct / n
    ci_lo, ci_hi = _wilson_ci(k_correct, n)
    from datetime import UTC, datetime

    return {
        "rate": rate,
        "n": n,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "horizon_bucket": bucket,
        "as_of": datetime.now(UTC).isoformat(),
        "signal_type": signal_type,
        "direction": direction,
    }


def list_active_base_rates(cx: sqlite3.Connection) -> list[dict[str, Any]]:
    """Liste tous les buckets qui ont assez de data pour servir un base rate.
    Useful pour dashboard ('voici les buckets ou le scorer peut tomber sur
    une stat empirique vs continuer a estimer en aveugle')."""
    active = []
    # Enumere les combinaisons (signal_type, direction, horizon_bucket) qui
    # ont >= MIN_N_PER_BUCKET. Brute force ok (peu de combinations).
    types = cx.execute(
        "SELECT DISTINCT signal_type FROM predictions WHERE signal_type IS NOT NULL"
    ).fetchall()
    type_list = [t[0] for t in types] + [None]  # None = all-types aggregate
    for st in type_list:
        for direction in ("bullish", "bearish"):
            for lo, _hi in HORIZON_BUCKETS:
                rate = get_empirical_base_rate(cx, st, direction, lo)
                if rate is not None:
                    active.append(rate)
    return active
