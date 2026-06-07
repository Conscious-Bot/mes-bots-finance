"""Source canonique unique pour seuils macro + tooltips + classifier thresholds.

Lecteurs :
 - dashboard/render.py : _MACRO_BANDS + _MACRO_TIPS (legacy dicts, exposed via accessors ici)
 - intelligence/macro_regime.py : classifier _VIX_STRESS / _HY_STRESS / etc.
 - intelligence/macro_book_warnings.py : rules R1-R5 thresholds

Source : config/calibration.yaml. Audit refresh tous les 10j via cron
audit_calibration_job (Phase B) qui ecrit docs/calibration_audits/.

API :
 - load_calibration() -> dict full yaml
 - get_band(indicator) -> (warn, danger, hi_bad) tuple
 - get_all_bands() -> dict miroir _MACRO_BANDS legacy
 - get_tooltip(indicator) -> str
 - get_all_tooltips() -> dict miroir _MACRO_TIPS legacy
 - get_classifier_threshold(name) -> float (ex 'VIX_STRESS')
 - get_rule_threshold(name) -> float (ex 'R1_semis_share_min')
 - get_audit_metadata() -> dict
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_CALIB_YAML = Path(__file__).resolve().parent.parent / "config" / "calibration.yaml"
_CACHE: dict | None = None


def load_calibration() -> dict:
    """Lazy load + cache. Redemarrage process suffit pour reload."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        import yaml
        with open(_CALIB_YAML) as f:
            _CACHE = yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"calibration.yaml load failed: {e}")
        _CACHE = {}
    return _CACHE


def get_band(indicator: str) -> tuple[float, float, bool] | None:
    """(warn, danger, hi_bad) ou None si indicator pas configure."""
    cfg = load_calibration().get("bands", {})
    b = cfg.get(indicator)
    if not b:
        return None
    return (float(b["warn"]), float(b["danger"]), bool(b["hi_bad"]))


def get_all_bands() -> dict[str, tuple[float, float, bool]]:
    """Dict miroir _MACRO_BANDS legacy. render.py import remplace par cet appel."""
    cfg = load_calibration().get("bands", {})
    out: dict[str, tuple[float, float, bool]] = {}
    for ind, b in cfg.items():
        try:
            out[ind] = (float(b["warn"]), float(b["danger"]), bool(b["hi_bad"]))
        except (KeyError, TypeError, ValueError) as e:
            log.warning(f"calibration.yaml malformed band for {ind}: {e}")
    return out


def get_tooltip(indicator: str) -> str:
    """Texte tooltip FR pour un indicateur, ou '' si absent."""
    cfg = load_calibration().get("tooltips", {})
    return cfg.get(indicator, "")


def get_all_tooltips() -> dict[str, str]:
    """Dict miroir _MACRO_TIPS legacy."""
    return dict(load_calibration().get("tooltips", {}))


def get_classifier_threshold(name: str) -> float | None:
    """Threshold utilise par macro_regime classifier (ex 'VIX_STRESS')."""
    cfg = load_calibration().get("classifier_thresholds", {})
    v = cfg.get(name)
    return float(v) if v is not None else None


def get_rule_threshold(name: str) -> float | None:
    """Threshold utilise par macro_book_warnings rules (ex 'R1_semis_share_min')."""
    cfg = load_calibration().get("rules_thresholds", {})
    v = cfg.get(name)
    return float(v) if v is not None else None


def get_audit_metadata() -> dict:
    """Date dernier audit + version + sources. Affichable dans dashboard footer."""
    return dict(load_calibration().get("audit_metadata", {}))


def get_temporal_splits() -> dict:
    """Splits temporels stricts (Phase 1.4 absorption_roadmap, doctrine L16).

    Returns dict avec train_window / val_window / oos_window / next_oos_window
    / rule. Vide {} si bloc absent (signal de violation L16 -- gate par
    test_calibration_temporal_splits_present).

    Lecteurs probables : footer dashboard ('calib v5 · OOS frozen jusqu'au
    2026-09-30'), audit cron (verifie qu'on n'est pas en periode frozen avant
    de proposer un re-tune), pre-commit hook futur.
    """
    return dict(get_audit_metadata().get("temporal_splits", {}))


# === Accessors sections "autres panels" (06/06 extension audit pro) ===


def get_rsi_bands() -> dict:
    """Seuils RSI(14) OB/OS pour _market_rsi.
    Returns {overbought_warn, overbought_danger, oversold_warn, oversold_danger, cache_ttl_seconds}."""
    return dict(load_calibration().get("rsi_bands", {}))


def get_breadth_bands() -> dict:
    """Seuils RSP/SPY vs MA50 pour _breadth_rsp_spy.
    Returns {large_calm_min, narrow_warn_max, narrow_danger_max, ma_window_days}."""
    return dict(load_calibration().get("breadth_bands", {}))


def get_risk_thresholds() -> dict:
    """Seuils Risque panel pour _rows_risque.
    Returns {near_stop_pct, watch_zone_pct, tension_scale, bar_full_at_pct}."""
    return dict(load_calibration().get("risk_thresholds", {}))


def get_concentration_caps() -> dict:
    """Caps concentration (line par conviction, sector, narrative, cluster).
    Returns full nested dict."""
    return dict(load_calibration().get("concentration_caps", {}))


def get_drawdown_thresholds() -> dict:
    """Seuils drawdown + vol_scaling.
    Returns {reduce_at_pct, stop_at_pct, max_open_positions, vol_scaling_*}."""
    return dict(load_calibration().get("drawdown_thresholds", {}))


def get_grade_bands() -> dict:
    """Mapping score -> letter (A+/A/A-/B+/...).
    Returns dict {A_plus: 90, A: 85, ...}."""
    return dict(load_calibration().get("grade_bands", {}))


def get_grade_gates() -> dict:
    """Caps appliques au score overall avant score_to_grade (hard gates).
    Returns dict {cluster_cap_over_2x_cap: 65, calibrage_under_50_cap: 60, ...}."""
    return dict(load_calibration().get("grade_gates", {}))


def reset_cache() -> None:
    """Force reload au prochain appel (tests + edge cases)."""
    global _CACHE
    _CACHE = None
