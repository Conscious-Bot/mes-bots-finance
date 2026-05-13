"""Macro/sentiment data wrappers.

- yfinance: VIX, DXY (no key)
- FRED API (optional, FRED_API_KEY env): yield curve, M2, RRP, TGA
- alternative.me: BTC Fear & Greed (no key)

Degrade gracefully when keys missing.
"""

import os
from pathlib import Path as _MacPath

import requests
import yfinance as yf
from dotenv import load_dotenv as _load_dotenv

_load_dotenv(str(_MacPath(__file__).parent.parent / ".env"))

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _fred_series(series_id, limit=1):
    """Fetch latest observation(s) from FRED. Returns list of {date, value} or None."""
    if not FRED_KEY:
        return None
    try:
        r = requests.get(
            FRED_BASE,
            params={
                "series_id": series_id,
                "api_key": FRED_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=10,
        )
        data = r.json()
        obs = data.get("observations", [])
        result = []
        for o in obs:
            v = o.get("value", ".")
            if v == ".":
                continue
            result.append({"date": o["date"], "value": float(v)})
        return result if result else None
    except Exception as e:
        print(f"FRED error for {series_id}: {e}")
        return None


def get_vix():
    try:
        t = yf.Ticker("^VIX")
        h = t.history(period="5d", interval="1d")
        if h.empty:
            return None
        return float(h["Close"].iloc[-1])
    except Exception:
        return None


def get_dxy():
    try:
        t = yf.Ticker("DX-Y.NYB")
        h = t.history(period="5d", interval="1d")
        if h.empty:
            return None
        return float(h["Close"].iloc[-1])
    except Exception:
        return None


def get_yield_curve_spread():
    """10Y-2Y Treasury spread (T10Y2Y). Negative = inverted = late cycle signal."""
    obs = _fred_series("T10Y2Y")
    if obs:
        return {"date": obs[0]["date"], "spread_pct": obs[0]["value"]}
    return None


def get_m2_yoy():
    """M2 YoY % change via M2SL. >5% = loose money. <0% = tight."""
    obs = _fred_series("M2SL", limit=13)
    if not obs or len(obs) < 13:
        return None
    current = obs[0]["value"]
    year_ago = obs[12]["value"]
    return {
        "date": obs[0]["date"],
        "yoy_pct": (current - year_ago) / year_ago * 100,
        "current_b": current,
    }


def get_rrp():
    """Overnight Reverse Repo (RRPONTSYD). High = excess liquidity parked at Fed."""
    obs = _fred_series("RRPONTSYD")
    if obs:
        return {"date": obs[0]["date"], "value_b": obs[0]["value"]}
    return None


def get_btc_fear_greed():
    """BTC sentiment 0-100. >80 = extreme greed (sell zone for ton FOMO bias)."""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = r.json()
        d = data.get("data", [{}])[0]
        return {
            "value": int(d.get("value", 0)),
            "classification": d.get("value_classification", ""),
            "timestamp": d.get("timestamp", ""),
        }
    except Exception as e:
        print(f"Fear&Greed error: {e}")
        return None


def get_macro_snapshot():
    """All macro indicators in one call. Missing values = None."""
    return {
        "vix": get_vix(),
        "dxy": get_dxy(),
        "yield_curve": get_yield_curve_spread(),
        "m2_yoy": get_m2_yoy(),
        "rrp": get_rrp(),
        "btc_fng": get_btc_fear_greed(),
    }


if __name__ == "__main__":
    snap = get_macro_snapshot()
    print("=== Macro snapshot ===")
    print(f"VIX: {snap['vix']:.2f}" if snap["vix"] else "VIX: n/a")
    print(f"DXY: {snap['dxy']:.2f}" if snap["dxy"] else "DXY: n/a")
    if snap["yield_curve"]:
        yc = snap["yield_curve"]
        print(f"Yield curve 10Y-2Y: {yc['spread_pct']:+.2f}% ({yc['date']})")
    else:
        print("Yield curve: n/a (FRED key manquante ?)")
    if snap["m2_yoy"]:
        m = snap["m2_yoy"]
        print(f"M2 YoY: {m['yoy_pct']:+.2f}% (latest {m['date']}, ${m['current_b'] / 1000:.2f}T)")
    else:
        print("M2: n/a (FRED key manquante ?)")
    if snap["rrp"]:
        r = snap["rrp"]
        print(f"Overnight RRP: ${r['value_b']:.1f}B ({r['date']})")
    else:
        print("RRP: n/a (FRED key manquante ?)")
    if snap["btc_fng"]:
        fng = snap["btc_fng"]
        print(f"BTC Fear&Greed: {fng['value']} ({fng['classification']})")
    else:
        print("BTC F&G: n/a")


# === Phase 16: Credit markets ===


def _fetch_fred_credit_series(series_id, limit=30):
    import os

    import requests

    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        return None, "FRED_API_KEY missing"
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": limit},
            timeout=10,
        )
        data = r.json()
        obs = data.get("observations", [])
        valid = [(o["date"], float(o["value"])) for o in obs if o["value"] != "."]
        if not valid:
            return None, "no data"
        return valid, None
    except Exception as e:
        return None, str(e)


def _classify_hy_oas_bp(bp):
    if bp < 300:
        return "TIGHT"
    if bp < 450:
        return "NORMAL"
    if bp < 700:
        return "STRESSED"
    return "CRISIS"


def get_hy_oas():
    data, err = _fetch_fred_credit_series("BAMLH0A0HYM2", limit=30)
    if err:
        return {"error": err}
    current = data[0]
    m1 = data[min(22, len(data) - 1)]
    bp = current[1] * 100
    change_1m_bp = (current[1] - m1[1]) * 100
    return {
        "series": "HY OAS",
        "date": current[0],
        "bp": bp,
        "change_1m_bp": change_1m_bp,
        "classification": _classify_hy_oas_bp(bp),
    }


def get_ig_oas():
    data, err = _fetch_fred_credit_series("BAMLC0A0CM", limit=30)
    if err:
        return {"error": err}
    current = data[0]
    m1 = data[min(22, len(data) - 1)]
    bp = current[1] * 100
    change_1m_bp = (current[1] - m1[1]) * 100
    return {
        "series": "IG OAS",
        "date": current[0],
        "bp": bp,
        "change_1m_bp": change_1m_bp,
    }


def _interpret_credit(hy, ig):  # noqa: ARG001
    if "error" in hy:
        return "credit data unavailable"
    bp = hy.get("bp", 0)
    chg = hy.get("change_1m_bp", 0)
    parts = []
    if chg > 50:
        parts.append("widening rapidly (+" + (f"{chg:.0f}") + "bp 1m)")
    elif chg < -50:
        parts.append("tightening rapidly (" + (f"{chg:.0f}") + "bp 1m)")
    if bp < 300:
        parts.append("historically tight (risk-on)")
    elif bp >= 700:
        parts.append("crisis-level stress")
    elif bp >= 500:
        parts.append("elevated stress (recession watch)")
    return "; ".join(parts) if parts else "spreads stable at current level"


def get_credit_regime():
    hy = get_hy_oas()
    ig = get_ig_oas()
    if "error" in hy:
        return {"error": hy["error"]}
    return {
        "hy": hy,
        "ig": ig,
        "overall": hy.get("classification", "unknown"),
        "interpretation": _interpret_credit(hy, ig),
    }


def format_credit_regime(reg):
    if "error" in reg:
        return "Credit data unavailable: " + reg["error"]
    hy = reg["hy"]
    ig = reg["ig"]
    lines = ["CREDIT REGIME: " + reg["overall"], ""]
    sign_hy = "+" if hy["change_1m_bp"] >= 0 else ""
    lines.append(
        "HY OAS: " + ("{:.0f}".format(hy["bp"])) + "bp  (1m " + sign_hy + ("{:.0f}".format(hy["change_1m_bp"])) + "bp)"
    )
    if "error" not in ig:
        sign_ig = "+" if ig["change_1m_bp"] >= 0 else ""
        lines.append(
            "IG OAS: "
            + ("{:.0f}".format(ig["bp"]))
            + "bp  (1m "
            + sign_ig
            + ("{:.0f}".format(ig["change_1m_bp"]))
            + "bp)"
        )
    lines.append("As of: " + hy["date"])
    lines.append("")
    lines.append("Read: " + reg["interpretation"])
    return "\n".join(lines)
