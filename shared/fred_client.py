"""Free FRED API wrapper for macro context lookups.

Doctrine memory `business_path_6_acted` : V4 macro enterre. Donc FRED
EST UNIQUEMENT pour enrichir le contexte d'une thèse existante (afficher
VIX/yields pour situational awareness), JAMAIS pour générer des signaux
de trade macro. Si tu te surprends à coder un cron macro signal,
relis la memory et stoppe.

Setup une fois :
  1. Free API key https://fred.stlouisfed.org/docs/api/api_key.html
  2. Add to .env : FRED_API_KEY=xxxx
  3. import shared.fred_client as fred ; fred.snapshot()

Tail-risk : FRED rate limit = 120 req/60s. On cache 1h pour rester tranquille.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from fredapi import Fred
except ImportError:
    Fred = None

REPO = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO / "data" / "fred_cache.json"
CACHE_TTL_S = 3600  # 1 hour

# Series IDs that matter for thesis context (curated, not exhaustive)
SERIES = {
    "VIXCLS": "VIX (CBOE Volatility Index, daily close)",
    "DGS10": "10Y Treasury yield (constant maturity)",
    "DGS2": "2Y Treasury yield",
    "T10Y2Y": "10Y-2Y spread (yield curve)",
    "DEXBZUS": "USD/BRL",
    "DEXJPUS": "JPY/USD",
    "DEXUSEU": "USD/EUR",
    "DCOILWTICO": "WTI crude oil price",
    "GOLDAMGBD228NLBM": "Gold (London PM fix)",
    "UNRATE": "US unemployment rate",
    "CPIAUCSL": "CPI all urban consumers",
    "FEDFUNDS": "Fed funds effective rate",
}


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, default=str))


def _client() -> Fred | None:
    if Fred is None:
        return None
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return None
    return Fred(api_key=key)


def latest(series_id: str) -> dict | None:
    """Latest observation for a series. Returns dict with value/date/series_label."""
    cache = _load_cache()
    now_ts = time.time()
    if series_id in cache and (now_ts - cache[series_id]["cached_at"]) < CACHE_TTL_S:
        return cache[series_id]["data"]

    c = _client()
    if c is None:
        return None
    try:
        s = c.get_series(series_id)
        if s.empty:
            return None
        val = float(s.iloc[-1])
        date = str(s.index[-1].date())
        data = {
            "series_id": series_id,
            "label": SERIES.get(series_id, "?"),
            "value": val,
            "as_of": date,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }
        cache[series_id] = {"cached_at": now_ts, "data": data}
        _save_cache(cache)
        return data
    except Exception as e:
        return {"series_id": series_id, "error": str(e)}


def snapshot() -> dict:
    """Snapshot of all curated series for situational awareness."""
    out = {}
    for sid in SERIES:
        out[sid] = latest(sid)
    return out


if __name__ == "__main__":
    snap = snapshot()
    for sid, data in snap.items():
        if data and "value" in data:
            print(f"  {sid:<25} {data['value']:>12.3f}  ({data['as_of']})  {data['label']}")
        else:
            print(f"  {sid:<25}  ERROR  {data}")
