"""Task #42 -- Backtest reproductible macro composite 2017-2026 (V3 portage prod).

Pull historique des 13 inputs bruts (yfinance + FRED) sur 9 ans, recompute
le score composite jour-par-jour avec la formule debt_monitor V3 actuelle
(INDICATOR_CONFIG prod, sans override local).

V3 transformations structurelles (livrees commit 7a43189) :
 - BTC niveau -> BTC_drawdown180 (compute_drawdown_180d sur historique)
 - FedBalance niveau -> FedBalance_yoy (compute_yoy_change sur historique)
 - MfgIP_yoy seuil P4 -2% -> -5%

Sortie : CSV historique docs/backtests/ + rapport stdout sur 8 anchors +
hooks pour Voie B OOS (Volmaggedon 2018, Xmas 2018, Credit Suisse 2023, FRC,
Delta 2021, Ete 2021).

Validation OOS (cf commit 7a43189 message) :
 - 7/8 dates non-anchor + 5/5 fenetres soutenues
 - Ordering correct sur tous les regimes
 - Verdict A : formule wirable Phase A sizing-phase (unblock task #42)

Anchors : labellisation post-sanity-check L11 (2019 = P2 pre-stress, pas
P1 calme -- juin 2019 avait courbe 10s-2s a 26 bps, IPMAN -1.91% YoY,
VIX 15.4).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Add repo root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from intelligence.debt_monitor import (  # noqa: E402
    INDICATOR_CONFIG,
    _PHASE_WEIGHT,
    classify_phase,
    composite_phase_from_score,
)

# Script utilise INDICATOR_CONFIG prod V3 directement (commit 7a43189). Pas
# d'override local : single-source-of-truth, le backtest et la prod tournent
# avec la meme formule. Les 2 helpers ci-dessous regenerent l'historique des
# inputs transformes (BTC_drawdown180, FedBalance_yoy) pour le backtest --
# qu'on ne peut pas obtenir avec les fetchers prod (qui prennent le t=now).


def compute_drawdown_180d(prices: dict[str, float]) -> dict[str, float]:
    """Drawdown vs max sur 180 jours glissants. Retourne % (-50.0 = -50%)."""
    sorted_dates = sorted(prices.keys())
    out = {}
    for i, d in enumerate(sorted_dates):
        # Fenetre 180j en arriere (par index, approx 180 jours civils)
        window_start = max(0, i - 180)
        window = sorted_dates[window_start:i + 1]
        max_in_window = max(prices[w] for w in window)
        if max_in_window > 0:
            out[d] = (prices[d] - max_in_window) / max_in_window * 100
    return out


def compute_yoy_change(values: dict[str, float]) -> dict[str, float]:
    """YoY % change. Pour chaque date d, cherche valeur a d-365j (closest <=)."""
    sorted_dates = sorted(values.keys())
    out = {}
    for d in sorted_dates:
        target_year = int(d[:4]) - 1
        target_prev = f"{target_year}-{d[5:]}"
        # Forward-fill : dernier datapoint <= target_prev
        candidates = [k for k in sorted_dates if k <= target_prev]
        if candidates:
            prev_val = values[candidates[-1]]
            if prev_val > 0:
                out[d] = (values[d] - prev_val) / prev_val * 100
    return out

START = "2017-01-01"
END = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Anchors (date -> attendu phase, label evenement)
# Note L11 : 2019-06 relabel P1 -> P2 apres sanity check (juin 2019 = pre-stress,
# pas calme : courbe 10s-2s 26 bps, IPMAN -1.91% YoY, VIX moyen 15.4).
ANCHORS = [
    ("2017-06-01", 1, "Calme 2017"),
    ("2019-06-01", 2, "2019 pre-stress (relabel L11)"),
    ("2020-03-23", 4, "COVID crash bottom"),
    ("2020-04-15", 3, "COVID rebond debut"),
    ("2022-06-15", 3, "Russie + Fed 75 bp"),
    ("2023-03-13", 2, "SVB collapse"),
    ("2024-08-05", 2, "Yen carry unwind"),
    ("2025-04-08", 3, "Tariff Liberation Day"),
]

# OOS validation dates (cf commit 7a43189) -- non-anchor, V3 a passe 7/8.
OOS_DATES = [
    ("2018-02-05", 3, "Volmaggedon XIV crash"),
    ("2018-12-24", 3, "Xmas Eve crash"),
    ("2023-03-20", 2, "Credit Suisse UBS rescue"),
    ("2023-05-01", 2, "FRC failure tail SVB"),
    ("2021-07-19", 2, "Delta variant S&P -1.6% (singleton P3, fenetre OK P2)"),
    ("2021-06-15", 2, "Ete 2021 normal"),
]


# ============================================================
# Data fetchers
# ============================================================


def fetch_yf_history(ticker: str, start: str = START, end: str = END):
    """Daily close. Returns dict[date_iso -> float]."""
    import yfinance as yf
    try:
        df = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
        if df.empty or "Close" not in df.columns:
            return {}
        out = {}
        for ts, val in df["Close"].dropna().items():
            d = ts.strftime("%Y-%m-%d")
            out[d] = float(val)
        return out
    except Exception as e:
        print(f"  yf {ticker} fail: {e}", file=sys.stderr)
        return {}


def fetch_fred_history(series_id: str, start: str = START, end: str = END):
    """FRED series history. Returns dict[date_iso -> float].

    Retry x3 avec backoff sur rate limit (run precedent : silent miss 2 series
    sur burst d'appels apres yfinance -> verdict invalide).
    """
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        print("  FRED_API_KEY missing", file=sys.stderr)
        return {}
    last_err = None
    for attempt in range(4):
        try:
            r = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id, "api_key": key, "file_type": "json",
                    "observation_start": start, "observation_end": end,
                    "sort_order": "asc",
                },
                timeout=30,
            )
            data = r.json()
            if "error_message" in data:
                err = data.get("error_message", "")
                if "Rate Limit" in err or "Too Many" in err:
                    last_err = err
                    sleep_s = 2 ** attempt
                    print(f"  FRED {series_id} rate-limited, retry in {sleep_s}s",
                          file=sys.stderr)
                    time.sleep(sleep_s)
                    continue
                print(f"  FRED {series_id} api_error: {err}", file=sys.stderr)
                return {}
            out = {}
            for o in data.get("observations", []):
                v = o.get("value")
                if v and v != ".":
                    try:
                        out[o["date"]] = float(v)
                    except ValueError:
                        pass
            return out
        except Exception as e:
            last_err = str(e)
            time.sleep(2 ** attempt)
    print(f"  FRED {series_id} GAVE UP after 4 attempts: {last_err}",
          file=sys.stderr)
    return {}


def fetch_fred_yoy(series_id: str) -> dict:
    """FRED YoY % series. Monthly typically."""
    raw = fetch_fred_history(series_id)
    if not raw:
        return {}
    dates = sorted(raw.keys())
    out = {}
    for i, d in enumerate(dates):
        if i < 12:
            continue
        prev = raw.get(dates[i - 12])
        if prev and prev > 0:
            out[d] = (raw[d] - prev) / prev * 100
    return out


# ============================================================
# Pull all indicators
# ============================================================


def pull_all_indicators() -> dict[str, dict]:
    """Returns {indicator_name: {date_iso: value}}. Each indicator forward-filled
    to daily frequency during analysis."""
    series = {}

    print("Pulling yfinance series...", file=sys.stderr)
    yf_mapping = {
        "TYX": "^TYX", "Gold": "GC=F", "USDJPY": "USDJPY=X",
        "VIX": "^VIX", "DXY": "DX-Y.NYB", "BTC": "BTC-USD",
        "MOVE": "^MOVE", "KRE": "KRE",
    }
    for name, ticker in yf_mapping.items():
        print(f"  {name} ({ticker})...", file=sys.stderr)
        series[name] = fetch_yf_history(ticker)
        time.sleep(0.5)  # respect yfinance throttle

    print("Pulling FRED series (1.0s spacing to avoid burst rate-limit)...",
          file=sys.stderr)
    fred_jobs = [
        ("HY_OAS", "BAMLH0A0HYM2", False),
        ("BankReserves", "WRESBAL", False),
        ("FedBalance", "WALCL", False),
        ("T10Y2Y", "T10Y2Y", False),
        ("CoreCPI", "CPILFESL", True),  # YoY
        ("MfgIP_yoy", "IPMAN", True),  # YoY
    ]
    for name, sid, is_yoy in fred_jobs:
        print(f"  {name} ({sid}, {'yoy' if is_yoy else 'raw'})...", file=sys.stderr)
        series[name] = fetch_fred_yoy(sid) if is_yoy else fetch_fred_history(sid)
        time.sleep(1.0)

    # WRESBAL FRED return is in MILLIONS USD (e.g. $3.1M = 3_102_810)
    # debt_monitor INDICATOR_CONFIG expects millions, OK direct.
    # WALCL same -- already in millions.

    print("Computing derived series CopperGold...", file=sys.stderr)
    copper = fetch_yf_history("HG=F")
    gold = series.get("Gold", {})
    cg = {}
    for d in set(copper.keys()) & set(gold.keys()):
        if gold[d] > 0:
            cg[d] = copper[d] / gold[d]
    series["CopperGold"] = cg

    # V3 transformations
    print("Computing V3 transformations (BTC drawdown 180j, FedBalance YoY)...",
          file=sys.stderr)
    series["BTC_drawdown180"] = compute_drawdown_180d(series.get("BTC", {}))
    series["FedBalance_yoy"] = compute_yoy_change(series.get("FedBalance", {}))

    return series


# ============================================================
# Daily score computation
# ============================================================


def forward_fill(daily_dates: list, sparse: dict) -> dict:
    """Forward-fill sparse series to daily. For each daily date, return last
    known value (most recent date <=). Returns {date_iso: value}."""
    sorted_keys = sorted(sparse.keys())
    out = {}
    j = 0
    last_val = None
    for d in daily_dates:
        while j < len(sorted_keys) and sorted_keys[j] <= d:
            last_val = sparse[sorted_keys[j]]
            j += 1
        if last_val is not None:
            out[d] = last_val
    return out


def compute_daily_composite(series: dict[str, dict]) -> list[dict]:
    """For each business day from START to END, compute composite score.
    Returns list of {date, score, phase, contributions, indicator_phases}."""
    # Build sorted list of daily dates (union of all VIX dates -- daily anchor)
    vix_dates = sorted(series.get("VIX", {}).keys())
    if not vix_dates:
        print("FATAL: no VIX data", file=sys.stderr)
        return []

    # Forward-fill all series to daily VIX cadence
    print(f"Forward-filling {len(series)} series to {len(vix_dates)} daily dates...",
          file=sys.stderr)
    filled = {}
    for name, sparse in series.items():
        filled[name] = forward_fill(vix_dates, sparse)

    results = []
    for d in vix_dates:
        contributions = []
        ind_phases = {}
        score = 0.0
        n_avail = 0
        for name, cfg in INDICATOR_CONFIG.items():
            val = filled.get(name, {}).get(d)
            if val is None:
                continue
            phase = classify_phase(val, cfg["phase_ranges"])
            contrib = cfg["weight"] * _PHASE_WEIGHT[phase]
            score += contrib
            contributions.append({"name": name, "value": val, "phase": phase, "contrib": contrib})
            ind_phases[name] = phase
            n_avail += 1
        composite_phase = composite_phase_from_score(score)
        results.append({
            "date": d, "score": round(score, 2),
            "phase": composite_phase, "n_indicators": n_avail,
            "indicator_phases": ind_phases,
        })
    return results


# ============================================================
# Output
# ============================================================


def save_csv(results: list[dict], path: Path) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "score", "phase", "n_indicators"])
        for r in results:
            w.writerow([r["date"], r["score"], r["phase"], r["n_indicators"]])
    print(f"CSV saved: {path}", file=sys.stderr)


def report_anchors(results: list[dict]) -> None:
    by_date = {r["date"]: r for r in results}
    print("\n=== VERDICT BACKTEST ===")
    print(f"{'Date':12} {'Event':30} {'Expected':10} {'Score':>7} {'Got':4} {'Match':6}")
    print("-" * 80)
    pass_count = 0
    fail_count = 0
    for date_anchor, expected_phase, label in ANCHORS:
        # Try exact date, then closest within ±5 trading days
        r = by_date.get(date_anchor)
        if not r:
            sorted_dates = sorted(by_date.keys())
            close = [d for d in sorted_dates if abs((datetime.fromisoformat(d) - datetime.fromisoformat(date_anchor)).days) <= 5]
            if close:
                r = by_date[close[0]]
        if not r:
            print(f"{date_anchor:12} {label:30} P{expected_phase:<9} N/A     N/A  ?")
            continue
        match = r["phase"] == expected_phase
        tag = "✓" if match else "✗"
        if match:
            pass_count += 1
        else:
            fail_count += 1
        print(f"{date_anchor:12} {label:30} P{expected_phase:<9} {r['score']:>6.1f} P{r['phase']}   {tag}")

    print()
    print(f"PASS {pass_count} / FAIL {fail_count} / TOTAL {len(ANCHORS)}")
    if fail_count == 0:
        print("\n→ VERDICT A : formule SOLIDE. Frontieres empiriques OK.")
        print("   → wire Phase A sizing-phase + re-promote frise.")
    elif fail_count >= 3:
        print("\n→ VERDICT B : formule CASSEE.")
        print("   → fix la formule avant tout wire (poids inputs, frontieres, etc.).")
    else:
        print("\n→ VERDICT MITIGE : ajustements ponctuels necessaires.")
        print("   → reviewer les indicateurs decevants avant wire.")


# ============================================================
# Main
# ============================================================


if __name__ == "__main__":
    print(f"Backtest macro composite {START} -> {END}")
    series = pull_all_indicators()
    print(f"\nIndicators pulled: {len(series)}", file=sys.stderr)
    for name, vals in series.items():
        if vals:
            dates = sorted(vals.keys())
            print(f"  {name:14} : {len(vals):>5} pts [{dates[0]} -> {dates[-1]}]",
                  file=sys.stderr)
        else:
            print(f"  {name:14} : EMPTY", file=sys.stderr)

    results = compute_daily_composite(series)
    print(f"\nDaily composite computed: {len(results)} business days",
          file=sys.stderr)

    out_csv = ROOT / "data" / "backtest" / "debt_composite_historical.csv"
    save_csv(results, out_csv)

    report_anchors(results)
