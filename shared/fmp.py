"""FinancialModelingPrep (FMP) — gateway canonique consensus targets / analyst ratings.

Wire 12/06/2026 (post audit data sources : LSEG/Daloopa trop chers, FMP free
tier 250 calls/jour avec consensus targets + ratings = bang/buck #1).

Free tier limites :
- 250 calls/jour (suffit pour 26 tickers × 3 endpoints = 78 calls/cycle daily)
- Données peuvent avoir lag 24-48h vs Bloomberg (acceptable pour gouvernance #135)

Use case PRESAGE :
- #135 refonte niveaux : consensus target externe live pour ancrer chaque thèse
- Stale_target_monitor : cross-check du target Olivier vs consensus rue
- Track-record alpha : F3 asymétrie sortie du ressenti

Endpoints utilisés (v3/v4) :
- /api/v3/price-target-consensus?symbol=TSLA : consensus mean/high/low/median
- /api/v3/price-target/{ticker} : derniers price targets analystes individuels
- /api/v4/upgrades-downgrades-consensus?symbol=TSLA : consensus buy/hold/sell
- /api/v3/analyst-estimates/{ticker} : forward EPS/revenue 4-8Q

Doctrine respectée :
- Gateway unique (jamais requests.get direct ailleurs dans le code)
- Datum return (value, asof, source, confidence) — fail-closed L15
- Cache mémoire TTL 1h (consensus bouge lentement, économise quota)
- Throttle quota tracking : 250/jour absolu
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from shared import config

log = logging.getLogger(__name__)

_API_BASE_V3 = "https://financialmodelingprep.com/api/v3"
_API_BASE_V4 = "https://financialmodelingprep.com/api/v4"
_CACHE_TTL = 3600  # 1h cache memoire
_TIMEOUT = 10

# Cache mémoire {(endpoint, ticker): (timestamp, response_dict)}
_CACHE: dict[tuple[str, str], tuple[float, Any]] = {}

# Quota tracking journalier
_QUOTA_DATE: str | None = None
_QUOTA_USED: int = 0
_QUOTA_LIMIT = 250


def _get_api_key() -> str | None:
    """Lit FMP_API_KEY depuis .env. None si pas configurée."""
    key = config.env("FMP_API_KEY", default=None)
    if not key:
        return None
    return str(key).strip() or None


def _quota_check() -> bool:
    """Returns True si le quota journalier le permet. Refresh compteur à minuit UTC."""
    global _QUOTA_DATE, _QUOTA_USED
    today = datetime.now(UTC).date().isoformat()
    if _QUOTA_DATE != today:
        _QUOTA_DATE = today
        _QUOTA_USED = 0
    return _QUOTA_USED < _QUOTA_LIMIT


def _quota_used() -> None:
    """Increment compteur quota."""
    global _QUOTA_USED
    _QUOTA_USED += 1


def quota_status() -> dict:
    """Returns dict {date, used, limit, remaining}. Pour audit/logging."""
    today = datetime.now(UTC).date().isoformat()
    used = _QUOTA_USED if _QUOTA_DATE == today else 0
    return {
        "date": today,
        "used": used,
        "limit": _QUOTA_LIMIT,
        "remaining": _QUOTA_LIMIT - used,
    }


def _fetch(endpoint_v: str, path: str, params: dict | None = None) -> Any:
    """GET FMP endpoint + cache + quota check. None si fail/quota/key absent."""
    key = _get_api_key()
    if not key:
        log.warning("FMP_API_KEY not configured (.env vide). Skipping.")
        return None
    if not _quota_check():
        log.warning(f"FMP quota daily exhausted ({_QUOTA_LIMIT} calls). Skipping.")
        return None

    cache_key = (path, str(params or {}))
    now = time.monotonic()
    hit = _CACHE.get(cache_key)
    if hit and (now - hit[0]) < _CACHE_TTL:
        return hit[1]

    base = _API_BASE_V3 if endpoint_v == "v3" else _API_BASE_V4
    url = f"{base}/{path}"
    full_params = {"apikey": key, **(params or {})}
    try:
        r = requests.get(url, params=full_params, timeout=_TIMEOUT)
        _quota_used()
        if r.status_code != 200:
            log.warning(f"FMP {path} HTTP {r.status_code}: {r.text[:120]}")
            return None
        data = r.json()
        _CACHE[cache_key] = (now, data)
        return data
    except Exception as e:
        log.warning(f"FMP {path} error: {e}")
        return None


# ─── Datum-like return wrappers ────────────────────────────────────────────────


@dataclass(frozen=True)
class PriceTargetConsensus:
    """Consensus analyst target d'un ticker. Tous prix en native currency du listing."""
    ticker: str
    target_mean: float | None
    target_median: float | None
    target_high: float | None
    target_low: float | None
    n_analysts: int | None
    asof: str
    source: str = "fmp"


@dataclass(frozen=True)
class AnalystRatings:
    """Consensus buy/hold/sell."""
    ticker: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    consensus_label: str  # "Strong Buy" / "Buy" / "Hold" / "Sell"
    asof: str
    source: str = "fmp"


# ─── Public gateway ────────────────────────────────────────────────────────────


def get_price_target_consensus(ticker: str) -> PriceTargetConsensus | None:
    """Consensus analyst price target (mean/median/high/low + n_analysts).

    Endpoint v3 /price-target-consensus.

    Returns None si :
    - FMP_API_KEY absent (.env vide)
    - Quota journalier épuisé
    - Ticker pas couvert par analystes (e.g. small-cap rare)
    - Network error
    """
    data = _fetch("v3", "price-target-consensus", {"symbol": ticker.upper()})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    row = data[0]
    return PriceTargetConsensus(
        ticker=ticker.upper(),
        target_mean=_safe_float(row.get("targetConsensus")),
        target_median=_safe_float(row.get("targetMedian")),
        target_high=_safe_float(row.get("targetHigh")),
        target_low=_safe_float(row.get("targetLow")),
        n_analysts=_safe_int(row.get("targetCount")) or _safe_int(row.get("numAnalysts")),
        asof=datetime.now(UTC).isoformat(),
    )


def get_analyst_ratings(ticker: str) -> AnalystRatings | None:
    """Consensus buy/hold/sell. Endpoint v4 /upgrades-downgrades-consensus."""
    data = _fetch("v4", "upgrades-downgrades-consensus", {"symbol": ticker.upper()})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    row = data[0]
    return AnalystRatings(
        ticker=ticker.upper(),
        strong_buy=_safe_int(row.get("strongBuy")) or 0,
        buy=_safe_int(row.get("buy")) or 0,
        hold=_safe_int(row.get("hold")) or 0,
        sell=_safe_int(row.get("sell")) or 0,
        strong_sell=_safe_int(row.get("strongSell")) or 0,
        consensus_label=str(row.get("consensus") or "?"),
        asof=datetime.now(UTC).isoformat(),
    )


def get_analyst_estimates(ticker: str, limit: int = 4) -> list[dict] | None:
    """Forward EPS/revenue estimates (4-8 quarters). Endpoint v3.

    Returns list de dicts {date, estimatedRevenueAvg, estimatedEpsAvg, ...}
    ou None si pas couvert / fail.
    """
    data = _fetch("v3", f"analyst-estimates/{ticker.upper()}", {"limit": limit})
    if not data or not isinstance(data, list):
        return None
    return data


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if f == 0:
            return None
        return f
    except Exception:
        return None


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None
