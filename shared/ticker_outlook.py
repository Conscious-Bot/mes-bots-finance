"""Source canonique pour l'outlook signaux per-ticker.

Aggregate les `predictions` (direction bullish/bearish) sur une fenetre
glissante. Consume par render.py (tooltip warn-chip enrichi avec
contexte signaux par ticker) et potentiellement /digest, /audit, etc.

Doctrine : orthogonal aux warnings macro_book (qui sont portfolio-level).
Ici on rapporte ce que les sources signalent SUR LE TICKER.
"""

from __future__ import annotations

import logging
import time as _t
from typing import TypedDict

from shared import storage

log = logging.getLogger(__name__)


class TickerOutlook(TypedDict):
    ticker: str
    bullish_n: int
    bearish_n: int
    total_n: int
    net_skew: int  # bullish_n - bearish_n
    latest_dir: str | None  # 'bullish' | 'bearish' | None
    latest_date: str | None  # ISO date


# Cache pour batch render (tout le panel utilise meme snapshot signals).
_CACHE: dict[tuple[str, int], TickerOutlook] | None = None
_CACHE_TS = 0.0
_TTL = 60.0


def recent_outlook(ticker: str, days: int = 30) -> TickerOutlook:
    """Aggregate predictions over days window. Returns counts + latest direction."""
    global _CACHE, _CACHE_TS
    now = _t.time()
    if _CACHE is None or (now - _CACHE_TS) > _TTL:
        _CACHE = {}
        _CACHE_TS = now
    key = (ticker.upper(), days)
    if key in _CACHE:
        return _CACHE[key]

    bullish_n = bearish_n = 0
    latest_dir: str | None = None
    latest_date: str | None = None
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT direction, date(created_at) AS d "
                "FROM predictions "
                "WHERE ticker = ? "
                "  AND created_at > datetime('now', '-' || ? || ' day') "
                "ORDER BY created_at DESC",
                (ticker.upper(), int(days)),
            ).fetchall()
        for r in rows:
            d = r[0]
            if d == "bullish":
                bullish_n += 1
            elif d == "bearish":
                bearish_n += 1
            if latest_dir is None:
                latest_dir = d
                latest_date = r[1]
    except Exception as e:
        log.warning(f"recent_outlook {ticker}: {e}")

    out = TickerOutlook(
        ticker=ticker.upper(),
        bullish_n=bullish_n,
        bearish_n=bearish_n,
        total_n=bullish_n + bearish_n,
        net_skew=bullish_n - bearish_n,
        latest_dir=latest_dir,
        latest_date=latest_date,
    )
    _CACHE[key] = out
    return out


def outlook_phrase(outlook: TickerOutlook) -> str:
    """Phrase courte FR pour affichage tooltip.

    Exemples :
      "Signaux 30j : 18 bullish / 20 bearish (net bearish 2)"
      "Signaux 30j : 5 bullish (aucun bearish)"
      "Aucun signal récent."
    """
    b, n = outlook["bullish_n"], outlook["bearish_n"]
    if b == 0 and n == 0:
        return "Aucun signal recent."
    skew = outlook["net_skew"]
    if skew > 2:
        sentiment = f"net bullish +{skew}"
    elif skew < -2:
        sentiment = f"net bearish {skew}"
    else:
        sentiment = "mixte"
    return f"Signaux 30j : {b} bullish / {n} bearish ({sentiment})."


def reset_cache() -> None:
    global _CACHE, _CACHE_TS
    _CACHE = None
    _CACHE_TS = 0.0
