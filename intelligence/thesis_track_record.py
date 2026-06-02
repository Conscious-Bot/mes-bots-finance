"""Tracking theses : lien explicite these <-> predictions liees.

Boucle prediction -> learning -> tracking -> theses cloturee :
  signal -> scoring V2 (trace #70) -> prediction sur ticker -> resolution
  -> Brier per source (#72) -> credibility recal (#76)
  -> alimente la these correspondante (ce module)

Pour chaque these active, on calcule :
  - n_predictions_linked : prédictions sur le ticker post opened_at
  - n_resolved, n_open
  - Brier moyen (rolling) + Wilson IC95
  - direction_alignment : % predictions alignees avec la direction these
  - posture : OK / WARN / ALERT selon Brier + alignment + drift

Sans ce module, le user voit le book mais pas "ma these NVDA gagne-t-elle
ou perd-elle empiriquement face aux signaux que je recois sur NVDA ?".
C'est l'unite minimale d'introspection these.
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any


def _wilson_ic95(n_correct: int, n_total: int) -> tuple[float, float]:
    """IC95 Wilson sur p = correct/total."""
    if n_total == 0:
        return 0.0, 1.0
    p = n_correct / n_total
    z = 1.96
    denom = 1 + z * z / n_total
    center = (n_correct + z * z / 2) / n_total / denom
    half = z * math.sqrt(p * (1 - p) / n_total + z * z / (4 * n_total * n_total)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def compute_thesis_track_record(
    cx: sqlite3.Connection,
    ticker: str,
    rolling_days: int | None = None,
) -> dict[str, Any] | None:
    """Pour la these active du ticker, compute les KPIs predictions linkees.

    Args:
        cx: connexion sqlite3
        ticker: ticker upper-case
        rolling_days: optionnel, restrict aux predictions avec
            baseline_date >= now - rolling_days (None = depuis opened_at)

    Returns:
        None si pas de these active. Sinon dict :
            thesis_id, ticker, conviction, direction, status,
            opened_at, entry_price, target_full, stop_price,
            n_predictions_linked, n_resolved, n_open,
            brier_avg (None si N<3), brier_ic95_low/high,
            direction_alignment_pct (None si 0 resolved),
            n_aligned, n_misaligned,
            posture : 'OK' / 'WARN' / 'ALERT' / 'INSUFFICIENT_DATA'

    Note : 'aligned' = direction prediction matche direction these.
    Pour bullish-bullish ou bearish-bearish = aligned.
    Pour bullish-bearish = misaligned.
    """
    ticker = ticker.upper()

    thesis_row = cx.execute(
        "SELECT id, ticker, conviction, direction, status, opened_at, "
        "       entry_price, target_full, stop_price "
        "FROM theses WHERE ticker=? AND status='active' "
        "ORDER BY id DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    if not thesis_row:
        return None

    if isinstance(thesis_row, dict):
        t = thesis_row
    else:
        t = {
            "id": thesis_row[0], "ticker": thesis_row[1],
            "conviction": thesis_row[2], "direction": thesis_row[3],
            "status": thesis_row[4], "opened_at": thesis_row[5],
            "entry_price": thesis_row[6], "target_full": thesis_row[7],
            "stop_price": thesis_row[8],
        }

    # Predictions liees : ticker match + baseline >= opened_at
    # Restrict optional sur rolling_days
    base_cond = "p.ticker = ? AND p.baseline_date >= ?"
    params: list[Any] = [ticker, t["opened_at"][:10] if t.get("opened_at") else "1970-01-01"]
    if rolling_days is not None:
        base_cond += " AND p.baseline_date >= datetime('now', ?)"
        params.append(f"-{rolling_days} days")

    rows = cx.execute(
        f"""SELECT p.id, p.direction, p.outcome, p.brier_score,
                   p.probability_at_creation, p.resolved_at
            FROM predictions p
            WHERE {base_cond}
              AND p.methodology_version != 'v0'""",
        params,
    ).fetchall()

    n_total = len(rows)
    if n_total == 0:
        return {
            **t,
            "n_predictions_linked": 0,
            "n_resolved": 0,
            "n_open": 0,
            "brier_avg": None,
            "brier_ic95_low": None,
            "brier_ic95_high": None,
            "direction_alignment_pct": None,
            "n_aligned": 0,
            "n_misaligned": 0,
            "posture": "INSUFFICIENT_DATA",
        }

    # Decompose
    n_resolved = 0
    n_open = 0
    brier_scores: list[float] = []
    n_aligned = 0
    n_misaligned = 0
    n_correct = 0
    thesis_direction = (t.get("direction") or "").lower()
    for r in rows:
        if isinstance(r, dict):
            pred = r
        else:
            pred = {
                "id": r[0], "direction": r[1], "outcome": r[2],
                "brier_score": r[3], "probability_at_creation": r[4],
                "resolved_at": r[5],
            }
        if pred.get("resolved_at"):
            n_resolved += 1
            if pred.get("brier_score") is not None and pred.get("outcome") in ("correct", "incorrect"):
                brier_scores.append(float(pred["brier_score"]))
                if pred["outcome"] == "correct":
                    n_correct += 1
        else:
            n_open += 1
        # Alignment (toutes les predictions, resolved ou non)
        pred_dir = (pred.get("direction") or "").lower()
        if thesis_direction and pred_dir:
            if pred_dir == thesis_direction:
                n_aligned += 1
            elif pred_dir in ("bullish", "bearish"):
                n_misaligned += 1

    n_directional = n_aligned + n_misaligned
    direction_alignment_pct = (
        round(n_aligned / n_directional * 100, 1) if n_directional > 0 else None
    )

    brier_avg = round(sum(brier_scores) / len(brier_scores), 4) if brier_scores else None
    ic95_low, ic95_high = (None, None)
    if brier_scores:
        lo, hi = _wilson_ic95(n_correct, len(brier_scores))
        ic95_low = round(lo, 3)
        ic95_high = round(hi, 3)

    # Posture
    if not brier_scores or len(brier_scores) < 3:
        posture = "INSUFFICIENT_DATA"
    elif brier_avg is not None and brier_avg <= 0.20 and (
        direction_alignment_pct is None or direction_alignment_pct >= 60
    ):
        posture = "OK"
    elif brier_avg is not None and brier_avg <= 0.25:
        posture = "WARN"
    else:
        posture = "ALERT"

    return {
        **t,
        "n_predictions_linked": n_total,
        "n_resolved": n_resolved,
        "n_open": n_open,
        "brier_avg": brier_avg,
        "brier_ic95_low": ic95_low,
        "brier_ic95_high": ic95_high,
        "direction_alignment_pct": direction_alignment_pct,
        "n_aligned": n_aligned,
        "n_misaligned": n_misaligned,
        "posture": posture,
    }


def compute_all_active_theses_track_record(
    cx: sqlite3.Connection,
    rolling_days: int | None = None,
) -> list[dict[str, Any]]:
    """Pour toutes les theses actives, retourne la liste des track records.
    Trie par n_resolved DESC (les mieux mesurees en premier)."""
    tickers = [r[0] for r in cx.execute(
        "SELECT DISTINCT ticker FROM theses WHERE status='active' ORDER BY ticker"
    ).fetchall()]
    out = []
    for tk in tickers:
        rec = compute_thesis_track_record(cx, tk, rolling_days=rolling_days)
        if rec is not None:
            out.append(rec)
    out.sort(key=lambda d: -d["n_resolved"])
    return out
