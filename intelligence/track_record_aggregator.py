"""Track record aggregator : single source of truth pour la page publique.

Combine tous les helpers livres 02/06 :
- intelligence.calibration_audit.compute_brier_by_source (#72)
- intelligence.calibration_audit.recalibrate_source_credibility (#76)
- intelligence.thesis_track_record.compute_all_active_theses_track_record
- intelligence.bias_track_record.compute_all_bias_track_records
- intelligence.benchmark.compute_alpha_vs_sox (existant)
- intelligence.calibration_audit.check_scorer_calibration (existant)

Returns un dict structure ready-to-render pour presage.pro/track.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any


def compute_public_track_record(
    cx: sqlite3.Connection,
    rolling_days: int = 180,
) -> dict[str, Any]:
    """Single source of truth pour la page publique track record.

    Args:
        cx: connexion sqlite3
        rolling_days: fenetre temporelle (default 180j)

    Returns:
        dict avec sections canoniques :
            as_of, rolling_days,
            predictions: {n_open, n_resolved, n_correct, brier_avg,
                          brier_status, calibration_status},
            bias_events: [{bias, total_delta, posture, ...}, ...],
            theses: {n_active, by_posture, top_alert_tickers},
            alpha: {book_return_pct, soxx_return_pct, alpha_pct,
                    median_age_days, window_months},
            sources: [{source_name, brier_avg, credibility, status, ...}, ...],
            methodology: {scorer_version, horizon_days_canonical,
                          bias_horizon_days, lock_in_thresholds},
            posture_global: 'OK' / 'WARN' / 'ALERT' / 'INSUFFICIENT_DATA'

    Defensive : chaque section catch ses propres erreurs et retourne un
    dict d'erreur sans crash de l'aggregator.
    """
    out: dict[str, Any] = {
        "as_of": datetime.now(UTC).isoformat(),
        "rolling_days": rolling_days,
    }

    # ─── Predictions section ─────────────────────────────────────────────
    try:
        pred_row = cx.execute(
            "SELECT "
            "  SUM(CASE WHEN resolved_at IS NULL THEN 1 ELSE 0 END) AS n_open, "
            "  SUM(CASE WHEN resolved_at IS NOT NULL THEN 1 ELSE 0 END) AS n_resolved, "
            "  SUM(CASE WHEN outcome='correct' THEN 1 ELSE 0 END) AS n_correct, "
            "  AVG(brier_score) AS brier_avg "
            "FROM predictions "
            "WHERE methodology_version != 'v0' "
            "AND (resolved_at IS NULL OR resolved_at >= datetime('now', ?))",
            (f"-{rolling_days} days",),
        ).fetchone()
        n_open = int(pred_row[0] or 0)
        n_resolved = int(pred_row[1] or 0)
        n_correct = int(pred_row[2] or 0)
        brier_avg = float(pred_row[3]) if pred_row[3] is not None else None
        if n_resolved < 5:
            brier_status = "INSUFFICIENT_DATA"
        elif brier_avg is not None and brier_avg <= 0.20:
            brier_status = "OK"
        elif brier_avg is not None and brier_avg <= 0.25:
            brier_status = "WARN"
        else:
            brier_status = "ALERT"
        out["predictions"] = {
            "n_open": n_open,
            "n_resolved": n_resolved,
            "n_correct": n_correct,
            "brier_avg": round(brier_avg, 4) if brier_avg is not None else None,
            "brier_status": brier_status,
            "accuracy_pct": round(n_correct / n_resolved * 100, 1) if n_resolved else None,
        }
    except Exception as e:
        out["predictions"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}

    # ─── Bias events section ────────────────────────────────────────────
    try:
        from intelligence.bias_track_record import compute_all_bias_track_records
        bias_recs = compute_all_bias_track_records(cx, rolling_days=rolling_days)
        out["bias_events"] = bias_recs
        # Cumul total cross-bias
        total_cumul = sum(b.get("total_delta_signed_eur", 0.0) for b in bias_recs)
        out["bias_total_delta_signed_eur"] = round(total_cumul, 2)
    except Exception as e:
        out["bias_events"] = []
        out["bias_total_delta_signed_eur"] = 0.0
        out["bias_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    # ─── Theses section ─────────────────────────────────────────────────
    try:
        from intelligence.thesis_track_record import (
            compute_all_active_theses_track_record,
        )
        all_theses = compute_all_active_theses_track_record(cx, rolling_days=rolling_days)
        by_posture: dict[str, int] = {"OK": 0, "WARN": 0, "ALERT": 0, "INSUFFICIENT_DATA": 0}
        for t in all_theses:
            by_posture[t.get("posture", "INSUFFICIENT_DATA")] = by_posture.get(
                t.get("posture", "INSUFFICIENT_DATA"), 0,
            ) + 1
        top_alerts = [
            {"ticker": t["ticker"], "brier_avg": t.get("brier_avg")}
            for t in all_theses
            if t.get("posture") == "ALERT"
        ][:5]
        out["theses"] = {
            "n_active": len(all_theses),
            "by_posture": by_posture,
            "top_alert_tickers": top_alerts,
        }
    except Exception as e:
        out["theses"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}

    # ─── Alpha section ──────────────────────────────────────────────────
    try:
        from intelligence.benchmark import compute_alpha_vs_sox
        months = max(1, rolling_days // 30)
        alpha = compute_alpha_vs_sox(months=months)
        if "error" not in alpha:
            out["alpha"] = {
                "book_return_pct": alpha.get("book_return_pct"),
                "bench_return_pct": alpha.get("bench_return_pct"),
                "bench_ticker": alpha.get("bench_ticker"),
                "alpha_pct": alpha.get("alpha_pct"),
                "median_position_age_days": alpha.get("median_position_age_days"),
                "window_months": alpha.get("months"),
            }
        else:
            out["alpha"] = {"error": alpha.get("error", "no_data")}
    except Exception as e:
        out["alpha"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}

    # ─── Sources section ────────────────────────────────────────────────
    try:
        from intelligence.calibration_audit import compute_brier_by_source
        sources = compute_brier_by_source(cx, days=rolling_days)
        out["sources"] = sources[:10]  # top 10
    except Exception as e:
        out["sources"] = []
        out["sources_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    # ─── Methodology disclosure ─────────────────────────────────────────
    try:
        from intelligence.lock_in_detector import (
            _HORIZON_DAYS as LOCK_IN_HORIZON,
            MAGNITUDE_THRESHOLD_BY_CONV,
            TARGET_PNL_BY_CONV,
        )
        out["methodology"] = {
            "scorer_version": "v2",
            "prediction_horizon_days": 28,
            "lock_in_horizon_days": LOCK_IN_HORIZON,
            "lock_in_targets_by_conv": TARGET_PNL_BY_CONV,
            "lock_in_magnitude_threshold_by_conv": {
                k: v for k, v in MAGNITUDE_THRESHOLD_BY_CONV.items()
                if v is not None
            },
            "credibility_recal_window_days": 180,
            "credibility_floor_ceiling": [0.30, 0.95],
        }
    except Exception as e:
        out["methodology"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}

    # ─── Posture globale ────────────────────────────────────────────────
    out["posture_global"] = _compute_global_posture(out)

    return out


def _compute_global_posture(record: dict[str, Any]) -> str:
    """Posture globale based sur sub-postures.
    ALERT si une section critique (predictions ou bias) est ALERT.
    WARN si une section est WARN sans ALERT.
    OK si tout est OK.
    INSUFFICIENT_DATA si predictions et bias_events sont tous deux insuf.
    """
    pred_status = record.get("predictions", {}).get("brier_status")
    bias_postures = [b.get("posture") for b in record.get("bias_events", [])]

    if pred_status == "ALERT" or "ALERT" in bias_postures:
        return "ALERT"
    if pred_status == "WARN" or "WARN" in bias_postures:
        return "WARN"
    if pred_status == "OK" or "OK" in bias_postures:
        return "OK"
    return "INSUFFICIENT_DATA"
