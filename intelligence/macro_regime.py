"""Phase A — Macro regime detector (deterministic, classifier pur).

Doctrine : independante du V3 composite score (HOLDOUT failed 02/06, demote
exploratoire). Detection par confluence d'indicateurs + dot classification
(green/yellow/red) deja en place. 5 regimes :

- COMPLACENT : vol ultra-basse + spreads serres + aucun stress.
  -> "calm before storm", melt-up risk.
- RISK_ON    : marche normal, vol moderee, spreads acceptables.
  -> default healthy regime.
- LATE_CYCLE : taux eleves + dollar fort + vol asleep.
  -> repricing risk monte mais pas encore d'unwind.
- FRAGILE    : 3+ indicateurs danger OU 6+ warn/danger AVEC vol asleep.
  -> "stress reel mais marche pas reveille" (le plus dangereux).
- STRESS     : VIX > 22 ou HY_OAS > 400 ou unwind carry actif.
  -> risk-off declare, posture defensive obligatoire.

API publique :
- classify_regime(readings) -> dict
- store_regime_reading(...) -> int | None
- latest_regime() -> dict | None
- check_regime_transition() -> dict
"""

from __future__ import annotations

import json
import logging
from typing import Literal, TypedDict

from shared import storage

log = logging.getLogger(__name__)

RegimeLabel = Literal["COMPLACENT", "RISK_ON", "LATE_CYCLE", "FRAGILE", "STRESS"]


class IndicatorReading(TypedDict):
    """Forme attendue d'un indicateur en input de classify_regime."""
    indicator: str
    value: float | None
    dot: str  # 'calm' | 'warn' | 'danger' | 'mute'


# Thresholds canoniques (alignes avec _MACRO_BANDS render.py v3 06/06 +5%).
_VIX_STRESS = 21.0        # v2 20 +5%
_VIX_LOW = 17.0           # v2 16 +5%
_VIX_COMPLACENT = 12.0    # v2 13 -5% (lower = harder to call complacent)
_HY_STRESS = 365.0        # v2 350 +5%
_HY_COMPLACENT = 210.0    # v2 220 -5%
_USDJPY_UNWIND = 161.0    # v2 153 +5% (passe au-dessus de la zone BoJ 160)
_TYX_HIGH = 4.2           # v2 4.0 +5%
_DXY_HIGH = 103.0         # v2 99 +5% (consistant avec band warn 103)


def _val(readings: dict[str, IndicatorReading], key: str) -> float | None:
    """Lookup safe : retourne value ou None."""
    r = readings.get(key)
    if r is None:
        return None
    v = r.get("value")
    return float(v) if v is not None else None


def classify_regime(readings: dict[str, IndicatorReading]) -> dict:
    """Classifier pur deterministique. Aucun side-effect, aucune DB.

    Input : dict {indicator_name: IndicatorReading}. Manquants tolérés.
    Output :
        {
          regime: RegimeLabel,
          triggers: list[str],  # rules qui ont fired (audit)
          danger_count, warn_count, asleep_count, silent_count
        }

    L4 critique : appel deux fois avec meme input -> meme output.
    """
    danger_count = sum(1 for r in readings.values() if r.get("dot") == "danger")
    warn_count = sum(1 for r in readings.values() if r.get("dot") == "warn")
    asleep_count = sum(1 for r in readings.values() if r.get("dot") == "calm")
    silent_count = sum(1 for r in readings.values() if r.get("dot") == "mute")

    vix = _val(readings, "VIX")
    hy = _val(readings, "HY_OAS")
    usdjpy = _val(readings, "USDJPY")
    tyx = _val(readings, "TYX")
    dxy = _val(readings, "DXY")

    triggers: list[str] = []

    # STRESS : risk-off declare.
    if vix is not None and vix > _VIX_STRESS:
        triggers.append(f"vix>{_VIX_STRESS}")
        return _result("STRESS", triggers, danger_count, warn_count, asleep_count, silent_count)
    if hy is not None and hy > _HY_STRESS:
        triggers.append(f"hy_oas>{_HY_STRESS}")
        return _result("STRESS", triggers, danger_count, warn_count, asleep_count, silent_count)
    if usdjpy is not None and usdjpy > _USDJPY_UNWIND and danger_count >= 3:
        triggers.append(f"usdjpy>{_USDJPY_UNWIND}+multi_danger")
        return _result("STRESS", triggers, danger_count, warn_count, asleep_count, silent_count)

    # FRAGILE : stress reel mais vol asleep (le plus piege).
    vix_asleep = vix is None or vix < _VIX_STRESS
    if danger_count >= 3 and vix_asleep:
        triggers.append(f"danger_count={danger_count}+vix_asleep")
        return _result("FRAGILE", triggers, danger_count, warn_count, asleep_count, silent_count)
    if (danger_count + warn_count) >= 6:
        triggers.append(f"warn+danger={danger_count + warn_count}>=6")
        return _result("FRAGILE", triggers, danger_count, warn_count, asleep_count, silent_count)

    # LATE_CYCLE : taux + dollar + vol basse.
    tyx_high = tyx is not None and tyx > _TYX_HIGH
    dxy_high = dxy is not None and dxy > _DXY_HIGH
    vix_low = vix is not None and vix < _VIX_LOW
    if tyx_high and dxy_high and vix_low:
        triggers.append("tyx_high+dxy_high+vix_low")
        return _result("LATE_CYCLE", triggers, danger_count, warn_count, asleep_count, silent_count)

    # COMPLACENT : vol ultra-basse + spreads serres + zero danger.
    if (
        vix is not None and vix < _VIX_COMPLACENT
        and hy is not None and hy < _HY_COMPLACENT
        and danger_count == 0
    ):
        triggers.append(f"vix<{_VIX_COMPLACENT}+hy<{_HY_COMPLACENT}+zero_danger")
        return _result("COMPLACENT", triggers, danger_count, warn_count, asleep_count, silent_count)

    # Default : RISK_ON.
    triggers.append("default")
    return _result("RISK_ON", triggers, danger_count, warn_count, asleep_count, silent_count)


def _result(
    regime: RegimeLabel,
    triggers: list[str],
    danger_count: int,
    warn_count: int,
    asleep_count: int,
    silent_count: int,
) -> dict:
    return {
        "regime": regime,
        "triggers": triggers,
        "danger_count": danger_count,
        "warn_count": warn_count,
        "asleep_count": asleep_count,
        "silent_count": silent_count,
    }


def store_regime_reading(
    regime: RegimeLabel,
    score: float,
    danger_count: int,
    warn_count: int,
    asleep_count: int,
    silent_count: int,
    triggers: list[str],
    notified: bool = False,
    transition: str | None = None,
) -> int | None:
    """Append row dans macro_regime_alerts via shared/storage."""
    return storage.insert_macro_regime_alert(
        regime=regime,
        score=score,
        danger_count=danger_count,
        warn_count=warn_count,
        asleep_count=asleep_count,
        silent_count=silent_count,
        triggers_json=json.dumps(triggers),
        notified=notified,
        transition=transition,
    )


def latest_regime() -> dict | None:
    """Lit la derniere row du journal via shared/storage."""
    row = storage.get_latest_macro_regime()
    if row is None:
        return None
    triggers_raw = row.get("triggers") or ""
    try:
        triggers = json.loads(triggers_raw) if triggers_raw else []
    except (json.JSONDecodeError, TypeError):
        triggers = []
    return {
        "regime": row["regime"],
        "score": float(row["score"]),
        "danger_count": int(row["danger_count"]),
        "warn_count": int(row["warn_count"]),
        "asleep_count": int(row["asleep_count"]),
        "silent_count": int(row["silent_count"]),
        "triggers": triggers,
        "created_at": row["created_at"],
        "transition": row["transition"],
    }


def check_regime_transition(
    readings: dict[str, IndicatorReading], score: float
) -> dict:
    """Classify courant + detecte transition vs derniere lecture + append.

    Returns: {regime, transition, prev_regime, stored_id}
    """
    classified = classify_regime(readings)
    prev = latest_regime()
    prev_regime = prev["regime"] if prev else None
    transition = "no_change" if prev_regime == classified["regime"] else "changed"
    stored_id = store_regime_reading(
        regime=classified["regime"],
        score=score,
        danger_count=classified["danger_count"],
        warn_count=classified["warn_count"],
        asleep_count=classified["asleep_count"],
        silent_count=classified["silent_count"],
        triggers=classified["triggers"],
        notified=False,
        transition=transition,
    )
    return {
        "regime": classified["regime"],
        "transition": transition,
        "prev_regime": prev_regime,
        "triggers": classified["triggers"],
        "stored_id": stored_id,
    }
