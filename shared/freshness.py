"""SLA fraicheur des inputs dates -- loader config/freshness.yaml + classifier.

Spec red-team 07/06 nuit++ premier-principe : stocke les inputs dates,
derive les outputs live. Chaque input porte (valeur, asof, source).

Doctrine M1 : le triple partout. Classification :
- green : sous green_sec -> input frais, derive sans warning
- amber : entre green et amber_sec -> warning "stale Ns" badge visible
- rouge : au-dela amber_sec -> L15 fail-closed sur calculs derives
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_YAML_PATH = _REPO_ROOT / "config" / "freshness.yaml"
_CACHE: dict | None = None

Severity = Literal["green", "amber", "rouge"]


def load_freshness_config() -> dict:
    """Charge config/freshness.yaml. Cache au boot."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        import yaml
        with open(_YAML_PATH) as f:
            _CACHE = yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"freshness.yaml load failed: {e}")
        _CACHE = {}
    return _CACHE


def clear_cache() -> None:
    global _CACHE
    _CACHE = None


def classify_age(category: str, age_seconds: float) -> Severity:
    """Classifie age en green / amber / rouge selon SLA.

    Args:
        category : 'price' / 'fx' / 'fundamentals' / 'macro'
        age_seconds : secondes ecoulees depuis asof

    Returns:
        'green' | 'amber' | 'rouge'

    Si category inconnue -> rouge (fail-closed L15).
    """
    cfg = load_freshness_config().get("slas", {})
    sla = cfg.get(category)
    if sla is None:
        log.warning(f"freshness category {category!r} unknown, return rouge L15")
        return "rouge"
    green = sla.get("green_sec", 0)
    amber = sla.get("amber_sec", 0)
    if age_seconds <= green:
        return "green"
    if age_seconds <= amber:
        return "amber"
    return "rouge"


def classify_asof(category: str, asof_iso: str) -> tuple[Severity, float]:
    """Classifie un asof ISO timestamp. Returns (severity, age_seconds).

    asof_iso : 'YYYY-MM-DDTHH:MM:SS+00:00' ou similar ISO.
    Si parse fail -> ('rouge', -1) (fail-closed).
    """
    try:
        asof = datetime.fromisoformat(asof_iso.replace("Z", "+00:00"))
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - asof).total_seconds()
    except Exception:
        return "rouge", -1.0
    return classify_age(category, age), age


def is_actionable(category: str, asof_iso: str) -> bool:
    """True si severity != 'rouge' (green/amber OK pour deriver, rouge = L15 refuse).

    Use case : valuation.position_valuation refuse de retourner value_eur
    si price.asof est rouge (fail-closed sur input stale).
    """
    sev, _ = classify_asof(category, asof_iso)
    return sev != "rouge"
