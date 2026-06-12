"""DEPRECATED 12/06/2026 — FMP free tier ne couvre que 19% du book PRESAGE
(5/26 tickers : TSLA, TSM, AMD, AMZN, GOOGL — méga-caps US seulement). Foreign
+ small/mid caps retournent HTTP 402 (Premium required).

Substitut canonique : `shared/prices.py:get_analyst_consensus(ticker)` via
yfinance .info qui couvre 100% du book (foreign tickers + small caps inclus).

Ce module est conservé comme reference historique / fallback potentiel pour
les méga-caps US si quota yfinance throttle un jour.

----

FinancialModelingPrep (FMP) — gateway canonique consensus targets / analyst ratings.

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

_API_BASE_STABLE = "https://financialmodelingprep.com/stable"
# Migration 12/06 (post-smoke FMP) : v3/v4 deprecates aout 2025, tout
# migre vers /stable/*. v3 retourne HTTP 403 "Legacy Endpoint".
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


def _fetch(path: str, params: dict | None = None) -> Any:
    """GET FMP /stable/{path} + cache + quota check. None si fail/quota/key absent."""
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

    url = f"{_API_BASE_STABLE}/{path}"
    full_params = {"apikey": key, **(params or {})}
    try:
        r = requests.get(url, params=full_params, timeout=_TIMEOUT)
        _quota_used()
        if r.status_code == 402:
            log.warning(f"FMP {path} 402: paid tier required")
            return None
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

    Endpoint /stable/price-target-consensus + /stable/price-target-summary
    (combo pour avoir n_analysts).

    Returns None si :
    - FMP_API_KEY absent (.env vide)
    - Quota journalier épuisé
    - Ticker pas couvert par analystes (e.g. small-cap rare)
    - Network error
    """
    data = _fetch("price-target-consensus", {"symbol": ticker.upper()})
    if not data or not isinstance(data, list) or not data[0]:
        return None
    row = data[0]
    # N analysts via price-target-summary (lastQuarterCount = window 90j)
    n = None
    summary = _fetch("price-target-summary", {"symbol": ticker.upper()})
    if summary and isinstance(summary, list) and summary[0]:
        n = _safe_int(summary[0].get("lastQuarterCount")) or _safe_int(
            summary[0].get("lastYearCount"),
        )
    return PriceTargetConsensus(
        ticker=ticker.upper(),
        target_mean=_safe_float(row.get("targetConsensus")),
        target_median=_safe_float(row.get("targetMedian")),
        target_high=_safe_float(row.get("targetHigh")),
        target_low=_safe_float(row.get("targetLow")),
        n_analysts=n,
        asof=datetime.now(UTC).isoformat(),
    )


def get_analyst_ratings(ticker: str) -> AnalystRatings | None:
    """Consensus buy/hold/sell. Endpoint /stable/grades-consensus."""
    data = _fetch("grades-consensus", {"symbol": ticker.upper()})
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
