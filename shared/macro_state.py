"""Source canonique unique pour l'etat macro courant.

Consolide les lectures de debt_signals + debt_composite + classify_regime
en un seul dict que TOUT panel/handler peut consommer. Avant ce module :
- _urgence panel calculait son propre dict
- 5+ queries SQL repetees a travers render.py
- macro_book_warnings reconstruisait l'input pour classify_regime

Apres : 1 lecture, 1 dict, N consommateurs (Vigie, Positions, Theses,
Risque, Urgence, /audit, /digest, ...).

Doctrine : single source of truth + readers pattern (cf
[[organize tout proprement]] memory 06/06).
"""

from __future__ import annotations

import logging
from typing import TypedDict

from intelligence.macro_regime import classify_regime
from shared import storage

log = logging.getLogger(__name__)


class IndicatorSnapshot(TypedDict):
    """Etat instantane d'un indicateur."""
    name: str
    value: float | None
    phase: int | None
    timestamp: str
    age_days: int


class MacroState(TypedDict):
    """Dict canonique consume par tous panels/handlers."""
    # Regime classifie (Phase A)
    regime: str  # 'COMPLACENT' | 'RISK_ON' | 'LATE_CYCLE' | 'FRAGILE' | 'STRESS'
    regime_triggers: list[str]

    # V3 composite (exploratoire mais affiche)
    score: float
    composite_phase: int  # 1-4 (STABLE/STRESS/ALERTE/CRISE)

    # Bucket triage cross-indicators (Phase C)
    bucket_counts: dict[str, int]  # {act, watch, calm, silent}

    # Indicateurs detail
    indicators: dict[str, IndicatorSnapshot]

    # Readings format prepare pour classify_regime (compat ascendant)
    readings_for_regime: dict[str, dict]


# Cache court (60s) pour eviter N appels DB par dashboard regen.
import time as _t

_CACHE: dict | None = None
_CACHE_TS = 0.0
_TTL = 60.0


def current_macro_state(force_refresh: bool = False) -> MacroState:
    """Snapshot canonique de l'etat macro courant.

    Returns un dict immutable-ish que tout consommateur peut utiliser.
    Cache 60s par defaut pour absorber les regen rapides du dashboard
    (PRESAGE_REFRESH = 60s).

    force_refresh=True pour bypass cache (utilise par /audit handler etc).
    """
    global _CACHE, _CACHE_TS
    now = _t.time()
    if not force_refresh and _CACHE is not None and (now - _CACHE_TS) < _TTL:
        return _CACHE  # type: ignore[return-value]

    state = _compute_state()
    _CACHE = state
    _CACHE_TS = now
    return state  # type: ignore[return-value]


def _compute_state() -> MacroState:
    """Compute from DB. Pas de side-effect (no INSERT, juste SELECT)."""
    import datetime as _dt

    indicators: dict[str, IndicatorSnapshot] = {}
    readings_for_regime: dict[str, dict] = {}
    today = _dt.date.today()

    # Bands import lazy pour eviter circular dep dashboard.render
    try:
        from dashboard.render import _MACRO_BANDS, _macro_dot
    except Exception:
        _MACRO_BANDS, _macro_dot = {}, None  # graceful degrade

    # Single source de verite pour debt_signals.
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT indicator_name, value, phase, timestamp FROM debt_signals "
                "WHERE id IN (SELECT MAX(id) FROM debt_signals GROUP BY indicator_name) "
                "ORDER BY timestamp DESC"
            ).fetchall()
    except Exception as e:
        log.warning(f"debt_signals read failed: {e}")
        rows = []

    bucket_counts = {"act": 0, "watch": 0, "calm": 0, "silent": 0}
    for ind, val, phase, ts in rows:
        try:
            age = (today - _dt.date.fromisoformat(str(ts)[:10])).days
        except Exception:
            age = 0
        v = float(val) if val is not None else None
        # Dot via band (canonical visual classifier).
        if v is None:
            dot = "mute"
        elif _macro_dot is not None:
            dot = _macro_dot(ind, v, phase)
        else:
            dot = "calm"
        indicators[ind] = IndicatorSnapshot(
            name=ind,
            value=v,
            phase=int(phase) if phase is not None else None,
            timestamp=str(ts),
            age_days=age,
        )
        readings_for_regime[ind] = {"indicator": ind, "value": v, "dot": dot}
        bucket = (
            "act" if dot == "danger"
            else "watch" if dot == "warn"
            else "silent" if dot == "mute"
            else "calm"
        )
        bucket_counts[bucket] += 1

    # Classify regime via canonical Phase A classifier.
    try:
        reg = classify_regime(readings_for_regime)
        regime_label = reg["regime"]
        regime_triggers = reg["triggers"]
    except Exception as e:
        log.warning(f"classify_regime failed: {e}")
        regime_label = "RISK_ON"
        regime_triggers = ["fallback"]

    # V3 composite (exploratoire).
    try:
        with storage.db() as cx:
            comp = cx.execute(
                "SELECT score, phase FROM debt_composite "
                "ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        if comp:
            score = float(comp[0] or 0)
            composite_phase = int(comp[1] or 1)
        else:
            score, composite_phase = 0.0, 1
    except Exception as e:
        log.warning(f"debt_composite read failed: {e}")
        score, composite_phase = 0.0, 1

    return MacroState(
        regime=regime_label,
        regime_triggers=regime_triggers,
        score=score,
        composite_phase=composite_phase,
        bucket_counts=bucket_counts,
        indicators=indicators,
        readings_for_regime=readings_for_regime,
    )


# Convenience accessors for panels that only need 1 piece.
def current_regime() -> str:
    """Just the regime label. Pour panels qui veulent juste afficher
    'STRESS' chip."""
    return current_macro_state()["regime"]


def current_composite_score() -> float:
    return current_macro_state()["score"]


def current_bucket_counts() -> dict[str, int]:
    return current_macro_state()["bucket_counts"]


# Color mapping canonique : regime label -> CSS class.
REGIME_COLOR_CLASS = {
    "COMPLACENT": "warn",  # melt-up risk
    "RISK_ON": "calm",
    "LATE_CYCLE": "warn",
    "FRAGILE": "warn",
    "STRESS": "bear",
}


def regime_color(regime: str) -> str:
    """Classe CSS canonique pour un label regime. Utilise par tout
    chip/badge qui affiche le regime."""
    return REGIME_COLOR_CLASS.get(regime, "steel")


def reset_cache() -> None:
    """Pour tests + force-refresh explicite."""
    global _CACHE, _CACHE_TS
    _CACHE = None
    _CACHE_TS = 0.0
